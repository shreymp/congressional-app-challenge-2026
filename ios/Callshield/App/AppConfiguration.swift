import Foundation
import Security
import SwiftUI

enum AppConfiguration {
    /// Normal launches always use production. Only Debug UI tests can select fixtures.
    static var isDemo: Bool {
        #if DEBUG
        // UI tests only; release builds always use the CALLSHIELD_DEMO build setting.
        if ProcessInfo.processInfo.arguments.contains("--ui-test-demo") { return true }
        if ProcessInfo.processInfo.arguments.contains("--ui-test-production") { return false }
        #endif
        return false // Normal launches always use the production app on every target.
    }

    /// Enable only after provisioning com.apple.developer.dialing-app on iOS 26.
    static var defaultDialerEnabled: Bool {
        (Bundle.main.object(forInfoDictionaryKey: "CallshieldDefaultDialerEnabled") as? String)?.lowercased() == "true"
    }

    /// LiveKit server host only, such as "myproject.livekit.cloud" (the app adds "wss://").
    /// Set CALLSHIELD_LIVEKIT_HOST in the gitignored Configuration/Local.xcconfig; nil until then.
    static var liveKitHost: String? {
        UserDefaults.standard.string(forKey: "callma.liveKitHost") ?? configuredString("CallshieldLiveKitHost")
    }

    /// Long-lived join token for the lobby room where the app waits for incoming calls.
    /// Set CALLSHIELD_LOBBY_TOKEN in the same file; nil until then. Never log it.
    static var lobbyToken: String? {
        ConnectionCredentials.token ?? configuredString("CallshieldLobbyToken")
    }

    static var outboundServiceURL: URL? {
        guard let raw = UserDefaults.standard.string(forKey: "callma.outboundURL"),
              let url = URL(string: raw), url.scheme == "https", url.host != nil else { return nil }
        return url
    }

    private static func configuredString(_ key: String) -> String? {
        let value = (Bundle.main.object(forInfoDictionaryKey: key) as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        return value?.isEmpty == false ? value : nil
    }
}


/// The device keeps its private lobby credential in Keychain, never in preferences.
enum ConnectionCredentials {
    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: (Bundle.main.bundleIdentifier ?? "callma") + ".calling",
         kSecAttrAccount as String: "lobby"]
    }
    static var token: String? {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        guard SecItemCopyMatching(request as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
    static func save(host: String, token: String) throws {
        let host = host.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let token = token.trimmingCharacters(in: .whitespacesAndNewlines)
        let labels = host.split(separator: ".", omittingEmptySubsequences: false)
        guard labels.count >= 2, labels.allSatisfy({ label in
            !label.isEmpty && label.count <= 63 && label.first != "-" && label.last != "-" &&
            label.utf8.allSatisfy { (97...122).contains($0) || (48...57).contains($0) || $0 == 45 }
        }), token.split(separator: ".").count == 3 else { throw SetupError.invalid }
        let data = Data(token.utf8)
        var status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var item = query
            item[kSecValueData as String] = data
            item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            status = SecItemAdd(item as CFDictionary, nil)
        }
        guard status == errSecSuccess else { throw SetupError.storage }
        UserDefaults.standard.set(host, forKey: "callma.liveKitHost")
        UserDefaults.standard.set(UUID().uuidString, forKey: "callma.connectionRevision")
    }
    enum SetupError: LocalizedError {
        case invalid, storage
        var errorDescription: String? {
            switch self {
            case .invalid: return "Enter the LiveKit host without a URL prefix and a valid lobby access token."
            case .storage: return "The access token couldn’t be saved securely. Try again."
            }
        }
    }
}

struct CallingConnectionView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var host = AppConfiguration.liveKitHost ?? ""
    @State private var token = ""
    @State private var error: String?
    @State private var outboundURL = AppConfiguration.outboundServiceURL?.absoluteString ?? ""
    var body: some View {
        NavigationStack {
            Form {
                Section("LiveKit connection") {
                    TextField("your-project.livekit.cloud", text: $host)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .keyboardType(.URL).accessibilityLabel("LiveKit host")
                    SecureField("Lobby access token", text: $token)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                    Text("Use the lobby token supplied by your callma. service. Never enter your LiveKit API secret.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section("Outgoing LiveKit calls") {
                    TextField("HTTPS calling gateway URL (optional)", text: $outboundURL)
                        .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                    Text("Your service must have an outbound SIP trunk. The LiveKit lobby token authenticates this gateway; no API secret belongs in the app.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section {
                    Text("Incoming calls ring while callma. is open. Outgoing calls use LiveKit when a calling gateway is configured. Otherwise they use the iPhone’s mobile service. This connection does not enable ringing when the app is closed.")
                    Text("The token is stored securely on this installation. A host and token identify a configuration; they do not confirm the service is online. Expired tokens must be replaced here.")
                }.font(.footnote).foregroundStyle(.secondary)
                if let error { Text(error).foregroundStyle(.red) }
                Button("Save Connection") {
                    do {
                        let credential = token.isEmpty ? AppConfiguration.lobbyToken ?? "" : token
                        let rawURL = outboundURL.trimmingCharacters(in: .whitespacesAndNewlines)
                        if !rawURL.isEmpty {
                            guard let url = URL(string: rawURL), url.scheme == "https", url.host != nil,
                                  url.user == nil, url.password == nil, url.query == nil, url.fragment == nil else {
                                throw ConnectionCredentials.SetupError.invalid
                            }
                        }
                        try ConnectionCredentials.save(host: host, token: credential)
                        UserDefaults.standard.set(rawURL, forKey: "callma.outboundURL")
                        dismiss()
                    } catch { self.error = error.localizedDescription }
                }.disabled(host.isEmpty || (token.isEmpty && AppConfiguration.lobbyToken == nil))
            }
            .scrollContentBackground(.hidden)
            .background(Palette.canvas).tint(Palette.accent)
            .navigationTitle("Calling Connection").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
        }
    }
}
