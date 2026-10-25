import SwiftUI

@main
struct CallmaApp: App {
    @AppStorage("callma.connectionRevision") private var connectionRevision = ""

    var body: some Scene {
        WindowGroup {
            if AppConfiguration.isDemo { DemoAppRoot() }
            else { ProductionRootView().id(connectionRevision) }
        }
    }
}

private struct DemoAppRoot: View {
    @StateObject private var store = CallmaStore()
    var body: some View { CallmaRootView().environmentObject(store) }
}
