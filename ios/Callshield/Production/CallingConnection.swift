import Foundation
import Security

/// Server-issued user session credential, separate from all Twilio account secrets.
enum CallingConnection {
    private static let service = "org.callshield.server-session"
    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
         kSecAttrAccount as String: "current-user"]
    }
    static var serverURL: URL? {
        guard let value = UserDefaults.standard.string(forKey: "callshield.serverURL"),
              let url = URL(string: value), url.scheme == "https", url.host != nil,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil else { return nil }
        return url
    }
    static var token: String? {
        var query = query
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
    static func save(server: String, token: String) throws {
        guard let url = URL(string: server.trimmingCharacters(in: .whitespacesAndNewlines)), url.scheme == "https", url.host != nil,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              !token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw CallingServiceError.configuration }
        let data = Data(token.trimmingCharacters(in: .whitespacesAndNewlines).utf8)
        let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var insertion = query
            insertion[kSecValueData as String] = data
            insertion[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            guard SecItemAdd(insertion as CFDictionary, nil) == errSecSuccess else { throw CallingServiceError.credential }
        } else if status != errSecSuccess { throw CallingServiceError.credential }
        UserDefaults.standard.set(url.absoluteString, forKey: "callshield.serverURL")
    }
    static func clear() { SecItemDelete(query as CFDictionary); UserDefaults.standard.removeObject(forKey: "callshield.serverURL") }
}

enum CallingServiceError: LocalizedError {
    case configuration, credential, server, invalidResponse, cancelled
    var errorDescription: String? {
        switch self {
        case .configuration: return "Enter an https:// server address and the session token issued by your Callshield server."
        case .credential: return "The connection credential couldn’t be saved securely."
        case .server: return "The calling server rejected the request. Check your connection and session token."
        case .invalidResponse: return "The calling server returned an invalid response."
        case .cancelled: return "The call was cancelled."
        }
    }
}

private final class CallingRedirectPolicy: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

struct CallingServiceClient {
    let baseURL: URL
    let credential: String
    private static let transport = URLSession(configuration: .ephemeral, delegate: CallingRedirectPolicy(), delegateQueue: nil)
    var session = transport
    struct Token: Decodable { let token: String; let identity: String }
    struct Subscription: Decodable {
        let audio_url: URL
        let bearer_token: String
        let caller_track: String
        let call_sid: String
        var configuration: CallerStreamConfiguration {
            .init(url: audio_url, bearerToken: bearer_token, callerTrack: caller_track, callSID: call_sid)
        }
    }
    func post<T: Decodable>(_ path: String, body: [String: String]) async throws -> T {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"; request.timeoutInterval = 10
        request.setValue("Bearer \(credential)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        // Credentials may never follow a redirect to an unrelated server.
        let data: Data, response: URLResponse
        (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, http.url?.host == baseURL.host,
              http.url?.scheme == "https", (200..<300).contains(http.statusCode), data.count < 64_000 else {
            throw CallingServiceError.server
        }
        do { return try JSONDecoder().decode(T.self, from: data) }
        catch { throw CallingServiceError.invalidResponse }
    }
}
