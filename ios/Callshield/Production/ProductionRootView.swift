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

    @AppStorage("callmaAppearance") private var appearance = "system"

    var body: some View {
        Group {
            if let call = store.active { ProductionCallView(call: call).transition(.opacity) }
            else {
                VStack(spacing: 0) {
                    HStack {
                        BrandWordmark()
                            .scaledFont(size: 12, weight: .semibold).foregroundStyle(Palette.accent)
                        Spacer()
                        if store.tab == .recents {
                            Button { store.showVoicemail = true } label: { Image(systemName: "recordingtape") }
                                .frame(width: 44, height: 44).foregroundStyle(Palette.accent)
                                .accessibilityLabel("Voicemail").accessibilityIdentifier("voicemailButton")
                        }
                    }
                    .frame(height: 26).padding(.horizontal, 23).padding(.top, 8)
                    HStack {
                        Text(store.tab.rawValue).scaledFont(size: 36, weight: .bold).tracking(-1.2).foregroundStyle(Palette.ink)
                            .accessibilityAddTraits(.isHeader)
                        Spacer()
                    }.padding(.horizontal, 23).padding(.top, 11).padding(.bottom, 19)
                    Group {
                        switch store.tab {
                        case .favorites: ProductionFavoritesView()
                        case .recents: ProductionRecentsView()
                        case .contacts: ProductionContactsView()
                        case .keypad: ProductionKeypadView()
                        case .settings: ProductionSettingsView()
                        }
                    }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                    HStack(spacing: 0) {
                        ForEach(PhoneTab.allCases, id: \.self) { tab in
                            Button { store.tab = tab } label: {
                                VStack(spacing: 4) {
                                    Image(systemName: tab.symbol).scaledFont(size: 23, weight: store.tab == tab ? .semibold : .regular)
                                    Text(tab.rawValue).font(.system(size: 11))
                                }
                                .frame(maxWidth: .infinity, minHeight: 50)
                                .background(store.tab == tab ? Palette.softAccent : Color.clear, in: RoundedRectangle(cornerRadius: 12))
                                .contentShape(Rectangle())
                                .foregroundStyle(store.tab == tab ? Palette.accent : Palette.secondary)
                            }
                            .buttonStyle(.plain)
                            .accessibilityIdentifier("productionTab\(tab.rawValue)")
                            .accessibilityAddTraits(store.tab == tab ? .isSelected : [])
                        }
                    }
                    .padding(.top, 9).padding(.bottom, 8)
                    .background(Palette.surface.ignoresSafeArea(edges: .bottom))
                    .overlay(alignment: .top) { Divider() }
                }
                .background(Palette.canvas.ignoresSafeArea())
                .tint(Palette.accent)
            }
        }
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.22), value: store.active?.id)
        .environmentObject(store)
        .environment(\.dynamicTypeSize, store.largeText ? .xxLarge : systemTextSize)
        .preferredColorScheme(appearance == "light" ? .light : appearance == "dark" ? .dark : nil)
        .sheet(item: $store.detail) { person in ProductionPersonDetail(person: person).environmentObject(store) }
        .sheet(item: $store.recordDetail) { record in ProductionPersonDetail(person: record.person, record: record).environmentObject(store) }
        .sheet(isPresented: $store.showVoicemail) { ProductionVoicemailView().environmentObject(store) }
        .alert(AppBrand.name, isPresented: Binding(get: { store.errorMessage != nil }, set: { if !$0 { store.errorMessage = nil } })) {
            Button("OK", role: .cancel) { store.errorMessage = nil }
        } message: { Text(store.errorMessage ?? "") }
        .task { await store.refresh() }
        .onDisappear {
            if let backend = store.coordinator.backend as? LiveKitCallingBackend {
                Task { await backend.shutDown() }
            }
        }
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

struct PhoneEmptyView: View {
    let symbol: String
    let title: String
    let message: String
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: symbol).scaledFont(size: 32).foregroundStyle(Palette.accent)
                .frame(width: 76, height: 76).background(Palette.softAccent, in: RoundedRectangle(cornerRadius: 24))
            Text(title).font(.title3.weight(.semibold)).foregroundStyle(Palette.ink)
            Text(message).font(.subheadline).foregroundStyle(Palette.secondary).multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 28).padding(.vertical, 48)
    }
}

