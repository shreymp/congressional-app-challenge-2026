import SwiftUI

@main
struct CallshieldApp: App {
    var body: some Scene {
        WindowGroup {
            if AppConfiguration.isDemo { DemoAppRoot() }
            else { ProductionRootView() }
        }
    }
}

private struct DemoAppRoot: View {
    @StateObject private var store = CallshieldStore()
    var body: some View { CallshieldRootView().environmentObject(store) }
}
