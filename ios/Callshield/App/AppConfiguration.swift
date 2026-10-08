import Foundation

enum AppConfiguration {
    /// Xcode → Callshield target → Build Settings → User-Defined → CALLSHIELD_DEMO.
    /// Set true for the TSX demo, false for the production interface, then rebuild.
    static var isDemo: Bool {
        #if DEBUG
        // UI tests only; release builds always use the Xcode build setting.
        if ProcessInfo.processInfo.arguments.contains("--ui-test-demo") { return true }
        if ProcessInfo.processInfo.arguments.contains("--ui-test-production") { return false }
        #endif
        return (Bundle.main.object(forInfoDictionaryKey: "CallshieldDemoMode") as? String)?.lowercased() == "true"
    }

    /// Enable only after provisioning com.apple.developer.dialing-app on iOS 26.
    static var defaultDialerEnabled: Bool {
        (Bundle.main.object(forInfoDictionaryKey: "CallshieldDefaultDialerEnabled") as? String)?.lowercased() == "true"
    }
}
