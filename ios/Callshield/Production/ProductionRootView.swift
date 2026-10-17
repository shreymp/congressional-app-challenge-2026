import Contacts
import Intents
import SwiftUI

struct ProductionRootView: View {
    @StateObject private var store: ProductionStore
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var systemTextSize

    init() {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--ui-test-production") {
            let store = ProductionStore(repository: MemoryPhoneRepository())
            if ProcessInfo.processInfo.arguments.contains("--ui-test-analysis") {
                let now = Date()
                store.active = PhoneCall(id: UUID(), person: PhoneNumber.person("+15555550100", name: "Analysis test"),
                    direction: .incoming, createdAt: now, connectedAt: now, stage: .connected, voice: .human,
                    deepfake: DeepfakeAssessment(state: .human, updatedAt: now, windows: 3),
                    transcript: TranscriptAssessment(state: .monitoring, updatedAt: now, probability: 0.94, scoredRevision: 8))
            }
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
                    HStack {
                        Label("Callshield", systemImage: "checkmark.shield")
                            .font(.system(size: 12, weight: .semibold)).foregroundStyle(Palette.green)
                        Spacer()
                        if store.tab == .recents {
                            Button { store.showVoicemail = true } label: { Image(systemName: "recordingtape") }
                                .frame(width: 44, height: 44).foregroundStyle(Palette.green)
                                .accessibilityLabel("Voicemail").accessibilityIdentifier("voicemailButton")
                        }
                    }
                    .frame(height: 26).padding(.horizontal, 23).padding(.top, 8)
                    HStack {
                        Text(store.tab.rawValue).font(.system(size: 36, weight: .bold)).tracking(-1.2).foregroundStyle(Palette.ink)
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
                                    Image(systemName: tab.symbol).font(.system(size: 23, weight: store.tab == tab ? .semibold : .regular))
                                    Text(tab.rawValue).font(.system(size: 9))
                                }
                                .frame(maxWidth: .infinity, minHeight: 50)
                                .contentShape(Rectangle())
                                .foregroundStyle(store.tab == tab ? Palette.green : Color(hex: 0xA1A4A9))
                            }
                            .buttonStyle(.plain)
                            .accessibilityIdentifier("productionTab\(tab.rawValue)")
                            .accessibilityAddTraits(store.tab == tab ? .isSelected : [])
                        }
                    }
                    .padding(.top, 9).padding(.bottom, 8)
                    .background(Color(hex: 0xFAFAFB).ignoresSafeArea(edges: .bottom))
                    .overlay(alignment: .top) { Divider() }
                }
                .background(Color.white.ignoresSafeArea())
                .tint(Palette.green)
            }
        }
        .environmentObject(store)
        .environment(\.dynamicTypeSize, store.largeText ? .xxLarge : systemTextSize)
        .preferredColorScheme(store.active == nil ? .light : .dark)
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

struct PhoneEmptyView: View {
    let symbol: String
    let title: String
    let message: String
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: symbol).font(.system(size: 34)).foregroundStyle(Color(hex: 0x8A9690))
            Text(title).font(.title3.weight(.semibold)).foregroundStyle(Color(hex: 0x34473C))
            Text(message).font(.subheadline).foregroundStyle(Palette.secondary).multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 28).padding(.vertical, 48)
    }
}

