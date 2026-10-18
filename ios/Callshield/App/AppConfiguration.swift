import Foundation

enum AppConfiguration {
    /// Xcode → Callshield target → Build Settings → User-Defined → CALLSHIELD_DEMO.
    /// Debug: true selects the TSX demo, false selects the real calling interface.
    /// Release always uses real calling and excludes development transcript tools.
    static var isDemo: Bool {
        #if DEBUG
        // Development and UI tests only.
        if ProcessInfo.processInfo.arguments.contains("--ui-test-demo") { return true }
        if ProcessInfo.processInfo.arguments.contains("--ui-test-production") { return false }
        return (Bundle.main.object(forInfoDictionaryKey: "CallshieldDemoMode") as? String)?.lowercased() == "true"
        #else
        return false
        #endif
    }

    /// Enable only after provisioning com.apple.developer.dialing-app on iOS 26.
    static var defaultDialerEnabled: Bool {
        (Bundle.main.object(forInfoDictionaryKey: "CallshieldDefaultDialerEnabled") as? String)?.lowercased() == "true"
    }
}
