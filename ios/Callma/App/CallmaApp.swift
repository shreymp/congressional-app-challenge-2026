import SwiftUI

@main
struct CallmaApp: App {
    var body: some Scene {
        WindowGroup {
            if AppConfiguration.isDemo { DemoAppRoot() }
            else { ProductionRootView() }
        }
    }
}

private struct DemoAppRoot: View {
    @StateObject private var store = CallmaStore()
    var body: some View { CallmaRootView().environmentObject(store) }
}
