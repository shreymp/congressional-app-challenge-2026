import SwiftUI

@main
struct CallshieldApp: App {
    @StateObject private var store = CallshieldStore()
    var body: some Scene {
        WindowGroup { CallshieldRootView().environmentObject(store) }
    }
}
