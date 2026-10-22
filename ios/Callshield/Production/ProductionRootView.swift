import Contacts
import Intents
import SwiftUI

struct ProductionRootView: View {
    @StateObject private var store: ProductionStore
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var systemTextSize
    @AppStorage(AppearanceChoice.storageKey) private var appearance = AppearanceChoice.system

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
            if let call = store.active { ProductionCallView(call: call) }
            else {
                VStack(spacing: 0) {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Wordmark()
                            Spacer()
                            if store.tab == .recents {
                                Button { store.showVoicemail = true } label: {
                                    Label("Voicemail", systemImage: "recordingtape")
                                        .font(.callout.weight(.semibold))
                                        .padding(.horizontal, 14).frame(minHeight: 44)
                                        .background(Theme.backgroundSurface, in: Capsule())
                                        .overlay(Capsule().strokeBorder(Theme.borderInteractive, lineWidth: 1))
                                }
                                .buttonStyle(.plain).foregroundStyle(Theme.textPrimary)
                                .accessibilityLabel("Voicemail").accessibilityIdentifier("voicemailButton")
                            }
                        }
                        .frame(minHeight: 44)
                        ScreenTitle(text: store.tab.rawValue)
                    }
                    .padding(.horizontal, Theme.margin).padding(.top, 4).padding(.bottom, 12)
                    Group {
                        switch store.tab {
                        case .favorites: ProductionFavoritesView()
                        case .recents: ProductionRecentsView()
                        case .contacts: ProductionContactsView()
                        case .keypad: ProductionKeypadView()
                        case .settings: ProductionSettingsView()
                        }
                    }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                    AppTabBar(tabs: PhoneTab.allCases, selection: $store.tab, title: \.rawValue, symbol: \.symbol,
                              identifier: { "productionTab\($0.rawValue)" })
                }
                .background(Theme.backgroundPrimary.ignoresSafeArea())
                .tint(Theme.actionAccent)
            }
        }
        .environmentObject(store)
        .environment(\.dynamicTypeSize, store.largeText ? max(systemTextSize, .xxLarge) : systemTextSize)
        .preferredColorScheme(appearance.colorScheme)
        .sheet(item: $store.detail) { person in ProductionPersonDetail(person: person).environmentObject(store) }
        .sheet(item: $store.recordDetail) { record in ProductionPersonDetail(person: record.person, record: record).environmentObject(store) }
        .sheet(isPresented: $store.showVoicemail) { ProductionVoicemailView().environmentObject(store) }
        .alert("Callshield", isPresented: Binding(get: { store.errorMessage != nil }, set: { if !$0 { store.errorMessage = nil } })) {
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
}

typealias PhoneEmptyView = EmptyStateView
