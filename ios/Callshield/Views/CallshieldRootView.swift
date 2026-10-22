import SwiftUI

struct CallshieldRootView: View {
    @EnvironmentObject private var store: CallshieldStore
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var systemTextSize
    @AppStorage(AppearanceChoice.storageKey) private var appearance = AppearanceChoice.system
    private let clock = Timer.publish(every: 0.1, on: .main, in: .common).autoconnect()

    var body: some View {
        ZStack {
            if let call = store.active {
                CallScreen(call: call)
            } else {
                VStack(spacing: 0) {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 12) {
                            toolbar
                            ScreenTitle(text: store.tab.rawValue).padding(.bottom, 4)
                            switch store.tab {
                            case .recents: RecentsScreen()
                            case .contacts: ContactsScreen()
                            case .settings: SettingsScreen()
                            }
                        }
                        .padding(.horizontal, Theme.margin)
                        .padding(.top, 4)
                        .padding(.bottom, 24)
                        .frame(maxWidth: 600)
                        .frame(maxWidth: .infinity)
                    }
                    .scrollIndicators(.hidden)
                    .scrollDismissesKeyboard(.interactively)
                    AppTabBar(tabs: AppTab.allCases, selection: $store.tab, title: \.rawValue,
                              symbol: { $0 == .recents ? "clock" : $0 == .contacts ? "person.2" : "gearshape" },
                              identifier: { "tab\($0.rawValue)" })
                }
                .background(Theme.backgroundPrimary.ignoresSafeArea())
                .foregroundStyle(Theme.textPrimary)
                .tint(Theme.actionAccent)
            }
        }
        .overlay(alignment: .bottom) {
            if !store.notice.isEmpty {
                Label(store.notice, systemImage: "checkmark.circle.fill")
                    .font(.body.weight(.medium))
                    .foregroundStyle(Theme.actionPrimaryText)
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.actionPrimary, in: RoundedRectangle(cornerRadius: 16))
                    .padding(.horizontal, Theme.margin)
                    .padding(.bottom, 84)
                    .accessibilityIdentifier("callNotice")
                    .allowsHitTesting(false)
            }
        }
        .sheet(item: $store.sheet) { sheet in
            DetailSheet(sheet: sheet)
                .environmentObject(store)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
        .environment(\.dynamicTypeSize, store.largeText ? max(systemTextSize, .xxLarge) : systemTextSize)
        .preferredColorScheme(appearance.colorScheme)
        .onReceive(clock) { now in
            if scenePhase == .active { store.tick(now: now) }
        }
        .onChange(of: scenePhase) { phase in
            if phase == .active { store.tick() }
        }
    }

    private var toolbar: some View {
        HStack {
            Wordmark()
            Spacer()
            Button { store.sheet = .demo } label: {
                Label("Try a call", systemImage: "play.fill")
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(Theme.actionPrimaryText)
                    .padding(.horizontal, 16)
                    .frame(minHeight: 44)
                    .background(Theme.actionPrimary, in: Capsule())
                    .contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Try an incoming demo call")
            .accessibilityIdentifier("demoButton")
        }
        .frame(minHeight: 44)
    }
}
