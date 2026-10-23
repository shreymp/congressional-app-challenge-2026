import SwiftUI

@main
struct CallshieldApp: App {
    @AppStorage("callma.connectionRevision") private var connectionRevision = ""

    var body: some Scene {
        WindowGroup {
            if AppConfiguration.isDemo { DemoAppRoot() }
            else { ProductionRootView().id(connectionRevision) }
        }
    }
}

private struct DemoAppRoot: View {
    @StateObject private var store = CallshieldStore()
    var body: some View { CallshieldRootView().environmentObject(store) }
}
