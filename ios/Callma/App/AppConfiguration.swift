import Foundation

enum AppConfiguration {
    /// Set CALLMA_DEMO in the gitignored Configuration/Local.xcconfig (default in
    /// Configuration/Callma.xcconfig), not in Xcode's Build Settings: a value set there is
    /// written to the tracked project.pbxproj and overrides both files.
    /// Set true for the TSX demo, false for the production interface, then rebuild.
    static var isDemo: Bool {
        #if DEBUG
        // UI tests only; release builds always use the CALLMA_DEMO build setting.
        if ProcessInfo.processInfo.arguments.contains("--ui-test-demo") { return true }
        if ProcessInfo.processInfo.arguments.contains("--ui-test-production") { return false }
        #endif
        return (Bundle.main.object(forInfoDictionaryKey: "CallmaDemoMode") as? String)?.lowercased() == "true"
    }

    /// Enable only after provisioning com.apple.developer.dialing-app on iOS 26.
    static var defaultDialerEnabled: Bool {
        (Bundle.main.object(forInfoDictionaryKey: "CallmaDefaultDialerEnabled") as? String)?.lowercased() == "true"
    }

    /// LiveKit server host only, such as "myproject.livekit.cloud" (the app adds "wss://").
    /// Set CALLMA_LIVEKIT_HOST in the gitignored Configuration/Local.xcconfig; nil until then.
    static var liveKitHost: String? { configuredString("CallmaLiveKitHost") }

    /// Long-lived join token for the lobby room where the app waits for incoming calls.
    /// Set CALLMA_LOBBY_TOKEN in the same file; nil until then. Never log it.
    static var lobbyToken: String? { configuredString("CallmaLobbyToken") }

    private static func configuredString(_ key: String) -> String? {
        let value = (Bundle.main.object(forInfoDictionaryKey: key) as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
        return value?.isEmpty == false ? value : nil
    }
}
