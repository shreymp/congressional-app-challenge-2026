import Foundation

struct TrustedGuardian: Identifiable, Codable, Equatable {
    var id: UUID = UUID()
    var name: String
    var number: String
}

struct ManualBlock: Identifiable, Codable, Equatable {
    var id: String { number }
    let number: String
    var name: String
    var serverSynced: Bool = false
    var removalPending: Bool = false
    var reportPending: Bool = false
}

struct SafetySnapshot: Codable, Equatable {
    var guardians: [TrustedGuardian] = []
    var blocks: [ManualBlock] = []
}

protocol SafetyRepository {
    func load() throws -> SafetySnapshot
    func save(_ snapshot: SafetySnapshot) throws
}

struct LocalSafetyRepository: SafetyRepository {
    let url: URL
    init(url: URL? = nil) {
        self.url = url ?? AppStoragePaths.file("safety-v1.json")
    }
    func load() throws -> SafetySnapshot {
        guard FileManager.default.fileExists(atPath: url.path) else { return SafetySnapshot() }
        return try JSONDecoder().decode(SafetySnapshot.self, from: Data(contentsOf: url))
    }
    func save(_ snapshot: SafetySnapshot) throws {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        var directory = url.deletingLastPathComponent()
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try directory.setResourceValues(values)
        try JSONEncoder().encode(snapshot).write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }
}

final class MemorySafetyRepository: SafetyRepository {
    var snapshot = SafetySnapshot()
    func load() throws -> SafetySnapshot { snapshot }
    func save(_ snapshot: SafetySnapshot) throws { self.snapshot = snapshot }
}

enum SafetyError: LocalizedError {
    case internationalNumber, noName, unconfigured, requestFailed(Int), invalidResponse
    var errorDescription: String? {
        switch self {
        case .internationalNumber: return "Use a full international number, such as +1 312 555 0123."
        case .noName: return "Enter the guardian’s name."
        case .unconfigured: return "The blocking and reporting service isn’t connected."
        case .requestFailed(let code): return "The blocking service couldn’t save this change (\(code)). Try again."
        case .invalidResponse: return "The blocking service returned an unreadable response. Try again."
        }
    }
}

enum SafetyNumber {
    static func canonical(_ raw: String) throws -> String {
        let normalized = try PhoneNumber.normalized(raw)
        let digits = normalized.dropFirst()
        guard normalized.first == "+", (8...15).contains(digits.count),
              digits.first != "0", digits.allSatisfy({ $0.isASCII && $0.isNumber }) else { throw SafetyError.internationalNumber }
        return normalized
    }

    static func matches(_ stored: String, _ incoming: String) -> Bool {
        guard let canonicalStored = try? canonical(stored) else { return false }
        if let canonicalIncoming = try? canonical(incoming) { return canonicalStored == canonicalIncoming }
        // Only local incoming forms use the existing US matching convention.
        // Explicit international numbers must never acquire an extra country code.
        guard canonicalStored.hasPrefix("+1"), canonicalStored.count == 12,
              let local = try? PhoneNumber.normalized(incoming), !local.hasPrefix("+") else { return false }
        return PhoneNumber.matches(canonicalStored, local)
    }
}

struct ServerBlock: Decodable, Equatable {
    let number: String
    let scope: String
}

@MainActor
protocol SafetyBackend {
    var isConfigured: Bool { get }
    func blocks() async throws -> [ServerBlock]
    func block(number: String, report: Bool) async throws
    func unblock(number: String) async throws
    func report(number: String, category: String) async throws
}

@MainActor
struct UnconnectedSafetyBackend: SafetyBackend {
    var isConfigured: Bool { false }
    func blocks() async throws -> [ServerBlock] { throw SafetyError.unconfigured }
    func block(number: String, report: Bool) async throws { throw SafetyError.unconfigured }
    func unblock(number: String) async throws { throw SafetyError.unconfigured }
    func report(number: String, category: String) async throws { throw SafetyError.unconfigured }
}

@MainActor
final class HTTPSafetyBackend: SafetyBackend {
    let baseURL: URL
    private let token: String
    private let session: URLSession
    var isConfigured: Bool { true }
    init(baseURL: URL, token: String, session: URLSession = .shared) {
        self.baseURL = baseURL; self.token = token; self.session = session
    }
    func blocks() async throws -> [ServerBlock] {
        struct Response: Decodable { let blocks: [ServerBlock] }
        return try JSONDecoder().decode(Response.self, from: await request(path: "v1/blocks", method: "GET")).blocks
    }
    func block(number: String, report: Bool) async throws {
        _ = try await request(path: "v1/blocks", method: "POST", body: ["number": number, "report": report, "category": "scam"])
    }
    func unblock(number: String) async throws {
        _ = try await request(path: "v1/blocks/" + number, method: "DELETE")
    }
    func report(number: String, category: String) async throws {
        _ = try await request(path: "v1/reports", method: "POST", body: ["number": number, "category": category])
    }
    private func request(path: String, method: String, body: [String: Any]? = nil) async throws -> Data {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = method
        request.timeoutInterval = 12
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse, data.count <= 1_000_000 else { throw SafetyError.invalidResponse }
        guard (200...299).contains(response.statusCode) else { throw SafetyError.requestFailed(response.statusCode) }
        return data
    }
    static func configured() -> SafetyBackend {
        // Test launches never connect to a real report/block server.
        if NSClassFromString("XCTestCase") != nil || ProcessInfo.processInfo.arguments.contains("--ui-test-production") {
            return UnconnectedSafetyBackend()
        }
        let environment = ProcessInfo.processInfo.environment
        let rawURL = environment["CALLMA_SAFETY_BASE_URL"] ?? environment["CALLSHIELD_SAFETY_BASE_URL"] ?? Bundle.main.object(forInfoDictionaryKey: "CallmaSafetyBaseURL") as? String
        let token = environment["CALLMA_SAFETY_TOKEN"] ?? environment["CALLSHIELD_SAFETY_TOKEN"] ?? Bundle.main.object(forInfoDictionaryKey: "CallmaSafetyToken") as? String
        guard let rawURL, let url = URL(string: rawURL), url.scheme == "https", url.host != nil,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              let token, !token.isEmpty, !token.contains("$(") else { return UnconnectedSafetyBackend() }
        return HTTPSafetyBackend(baseURL: url, token: token)
    }
}

enum GuardianMessage {
    /// An extractive preview. No generative model or new factual claims are used.
    static func draft(call: PhoneCall, includeExcerpt: Bool) -> String {
        var text = "Please check in with me. I’m on a call with \(call.person.name)"
        if !call.person.number.isEmpty { text += " (\(call.person.number))" }
        text += ". callma. suggested extra caution. Its experimental checks can be wrong."
        if includeExcerpt, let excerpt = call.transcript?.savedExcerpt?.trimmingCharacters(in: .whitespacesAndNewlines), !excerpt.isEmpty {
            text += "\n\nCaller transcript excerpt (automatic and may contain errors):\n" + String(excerpt.prefix(800))
        } else if includeExcerpt {
            text += "\n\nNo caller transcript is available to share."
        }
        text += "\n\nPlease contact me using my saved number."
        return text
    }
}
