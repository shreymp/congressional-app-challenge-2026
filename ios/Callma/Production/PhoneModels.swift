import Foundation

enum PhoneTab: String, CaseIterable {
    case favorites = "Favorites", recents = "Recents", contacts = "Contacts", keypad = "Keypad", settings = "Settings"
    var symbol: String {
        switch self {
        case .favorites: return "star"
        case .recents: return "clock"
        case .contacts: return "person.2"
        case .keypad: return "circle.grid.3x3"
        case .settings: return "gearshape"
        }
    }
}

enum CallDirection: String, Codable { case incoming, outgoing }
enum PhoneCallOutcome: String, Codable { case completed, missed, cancelled, failed, answeredElsewhere }

struct PhoneCallRecord: Identifiable, Codable, Equatable {
    let id: UUID
    let person: Person
    let date: Date
    let duration: Int
    let direction: CallDirection
    let outcome: PhoneCallOutcome
    let voice: Voice
    var deepfake: DeepfakeAssessment? = nil
    var transcript: TranscriptAssessment? = nil
}

struct PhoneCall: Identifiable, Equatable {
    enum Stage: String { case incoming, connecting, connected, held }
    let id: UUID
    var person: Person
    let direction: CallDirection
    let createdAt: Date
    var connectedAt: Date?
    var stage: Stage
    var voice: Voice = .unknown
    var muted = false
    var speaker = false
    var deepfake: DeepfakeAssessment? = nil
    var transcript: TranscriptAssessment? = nil
    var lastDeepfakeResult: DeepfakeAssessment? = nil
    var lastTranscriptResult: TranscriptAssessment? = nil
}

struct PhoneSnapshot: Codable {
    var history: [PhoneCallRecord] = []
    var favorites: [Person] = []
    var largeText = false
    var hiddenHistoryIDs: Set<UUID> = []
}

enum PhoneError: LocalizedError {
    case invalidNumber, serviceUnavailable, simulatorUnavailable, microphoneDenied, actionUnavailable
    var errorDescription: String? {
        switch self {
        case .invalidNumber: return "Enter a valid phone number."
        case .serviceUnavailable: return "Calling through callma. isn’t available yet. You can call using your mobile service."
        case .simulatorUnavailable: return "Phone calls require an iPhone. They aren’t available in the simulator."
        case .microphoneDenied: return "Allow microphone access in Settings to make a callma. call."
        case .actionUnavailable: return "That action isn’t available for this call."
        }
    }
}

enum PhoneNumber {
    /// Accept a phone number, not arbitrary URI input; never allow a callback URL to recurse.
    static func normalized(_ text: String) throws -> String {
        let allowed = CharacterSet(charactersIn: "+0123456789*# ()-.\u{00A0}")
        guard !text.isEmpty, text.count <= 64,
              text.unicodeScalars.allSatisfy({ allowed.contains($0) }) else { throw PhoneError.invalidNumber }
        let number = text.filter { "+0123456789*#".contains($0) }
        guard number.contains(where: { "0123456789".contains($0) }),
              number.count <= 32, number.filter({ $0 == "+" }).count <= 1,
              !number.dropFirst().contains("+") else { throw PhoneError.invalidNumber }
        return number
    }

    static func fromURL(_ url: URL) throws -> String {
        guard url.scheme?.lowercased() == "tel", url.host == nil, url.query == nil, url.fragment == nil,
              let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else { throw PhoneError.invalidNumber }
        return try normalized(components.path)
    }

    /// Match common US local and country-code forms without changing the dialed number.
    static func matches(_ first: String, _ second: String) -> Bool {
        func key(_ value: String) -> String? {
            guard let normalized = try? normalized(value),
                  !normalized.contains("*"), !normalized.contains("#") else { return nil }
            let digits = normalized.filter { $0.isNumber }
            if digits.count == 10 { return "1" + digits }
            return digits.isEmpty ? nil : digits
        }
        guard let left = key(first), let right = key(second) else { return false }
        return left == right
    }

    static func person(_ number: String, name: String? = nil) -> Person {
        let name = name?.trimmingCharacters(in: .whitespacesAndNewlines)
        let display = name?.isEmpty == false ? name! : number
        let initials = name?.isEmpty == false ? name!.split(separator: " ").prefix(2).compactMap(\.first).map(String.init).joined() : "?"
        return Person(name: display, number: number, initials: initials, color: .slate, voice: .unknown)
    }
}

