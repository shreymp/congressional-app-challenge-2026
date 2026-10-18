import SwiftUI

@main
struct CallshieldApp: App {
    var body: some Scene {
        WindowGroup {
            #if DEBUG
            if AppConfiguration.isDemo { DemoAppRoot() }
            else { ProductionRootView() }
            #else
            ProductionRootView()
            #endif
        }
    }
}

#if DEBUG
private struct DemoAppRoot: View {
    @StateObject private var store = CallshieldStore()
    var body: some View { CallshieldRootView().environmentObject(store) }
}

#endif
