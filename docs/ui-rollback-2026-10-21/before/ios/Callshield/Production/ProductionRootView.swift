import Contacts
import Intents
import SwiftUI

struct ProductionRootView: View {
    @StateObject private var store: ProductionStore
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var systemTextSize

    init() {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--ui-test-production") {
            let store = ProductionStore(repository: MemoryPhoneRepository())
            store.showAnalysisTestCall()
            _store = StateObject(wrappedValue: store)
            return
        }
        #endif
        _store = StateObject(wrappedValue: ProductionStore())
    }

    var body: some View {
        Group {
            if let call = store.active { ProductionCallView(call: call).id(call.id).transition(.opacity) }
            else {
                TabView(selection: $store.tab) {
                    ForEach(PhoneTab.allCases, id: \.self) { tab in
                        NavigationStack {
                            tabContent(tab)
                                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                                .background(Palette.canvas)
                                .navigationTitle(tab.rawValue)
                                .toolbar {
                                    if tab == .recents {
                                        ToolbarItem(placement: .navigationBarTrailing) {
                                            Button { store.showVoicemail = true } label: {
                                                Label("Voicemail", systemImage: "recordingtape")
                                            }
                                            .accessibilityIdentifier("voicemailButton")
                                        }
                                    }
                                }
                        }
                        .tabItem {
                            Label(tab.rawValue, systemImage: tab.symbol)
                                .accessibilityIdentifier("productionTab\(tab.rawValue)")
                        }
                        .tag(tab)
                    }
                }
                .tint(Palette.accent)
            }
        }
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.22), value: store.active?.id)
        .environmentObject(store)
        .environment(\.dynamicTypeSize, store.largeText && systemTextSize < .xxLarge ? .xxLarge : systemTextSize)
        .sheet(item: $store.detail) { person in ProductionPersonDetail(person: person).environmentObject(store) }
        .sheet(item: $store.recordDetail) { record in ProductionPersonDetail(person: record.person, record: record).environmentObject(store) }
        .sheet(isPresented: $store.showVoicemail) { ProductionVoicemailView().environmentObject(store) }
        .alert(AppBrand.name, isPresented: Binding(get: { store.errorMessage != nil }, set: { if !$0 { store.errorMessage = nil } })) {
            Button("OK", role: .cancel) { store.errorMessage = nil }
        } message: { Text(store.errorMessage ?? "") }
        .task { await store.refresh() }
        .onChange(of: scenePhase) { phase in if phase == .active { Task { await store.refresh() } } }
        .onReceive(NotificationCenter.default.publisher(for: .CNContactStoreDidChange)) { _ in Task { await store.refreshContacts() } }
        .onOpenURL { store.receive($0) }
        .onContinueUserActivity("INStartCallIntent") { activity in
            // A call from a withheld number sits in system Recents under a label, not a number; tapping it has nothing to dial.
            if let intent = activity.interaction?.intent as? INStartCallIntent,
               let number = intent.contacts?.first?.personHandle?.value,
               (try? PhoneNumber.normalized(number)) != nil { store.receiveNumber(number) }
        }
    }

    @ViewBuilder private func tabContent(_ tab: PhoneTab) -> some View {
        switch tab {
        case .favorites: ProductionFavoritesView()
        case .recents: ProductionRecentsView()
        case .contacts: ProductionContactsView()
        case .keypad: ProductionKeypadView()
        case .settings: ProductionSettingsView()
        }
    }

}

struct PhoneEmptyView: View {
    let symbol: String
    let title: String
    let message: String
    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: symbol).font(.largeTitle).foregroundStyle(Palette.secondary)
                .frame(width: 72, height: 72).background(Palette.surface, in: Circle())
                .accessibilityHidden(true)
            Text(title).font(.title3.weight(.semibold)).foregroundStyle(Palette.ink)
            Text(message).font(.body).foregroundStyle(Palette.secondary).multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 28).padding(.vertical, 56)
    }
}

