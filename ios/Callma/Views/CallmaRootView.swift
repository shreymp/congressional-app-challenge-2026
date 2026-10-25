import SwiftUI

struct CallmaRootView: View {
    @EnvironmentObject private var store: CallmaStore
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var systemTextSize
    private let clock = Timer.publish(every: 0.1, on: .main, in: .common).autoconnect()

    @AppStorage("callmaAppearance") private var appearance = "system"

    var body: some View {
        ZStack {
            if let call = store.active {
                CallScreen(call: call).transition(.opacity)
            } else {
                VStack(spacing: 0) {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 0) {
                            toolbar
                            Text(store.tab.rawValue)
                                .scaledFont(size: 36, weight: .bold)
                                .tracking(-1.2)
                                .accessibilityAddTraits(.isHeader)
                                .padding(.top, 11)
                                .padding(.bottom, 19)
                            switch store.tab {
                            case .favorites: DemoFavoritesScreen()
                            case .recents: RecentsScreen()
                            case .contacts: ContactsScreen()
                            case .keypad: DemoKeypadScreen()
                            case .settings: SettingsScreen()
                            }
                        }
                        .padding(.horizontal, 23)
                        .padding(.top, 8)
                        .padding(.bottom, 16)
                        .frame(maxWidth: 600)
                        .frame(maxWidth: .infinity)
                    }
                    .scrollIndicators(.hidden)
                    .scrollDismissesKeyboard(.interactively)
                    tabBar
                }
                .background(Palette.canvas.ignoresSafeArea())
                .foregroundStyle(Palette.ink)
            }
        }
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.22), value: store.active?.id)
        .overlay(alignment: .bottom) {
            if !store.notice.isEmpty {
                Label(store.notice, systemImage: "checkmark")
                    .scaledFont(size: 11)
                    .foregroundStyle(Palette.actionInk)
                    .padding(12)
                    .frame(maxWidth: .infinity)
                    .background(Palette.action, in: RoundedRectangle(cornerRadius: 12))
                    .padding(.horizontal, 15)
                    .padding(.bottom, 65)
                    .accessibilityIdentifier("callNotice")
                    .allowsHitTesting(false)
            }
        }
        .sheet(item: $store.sheet) { sheet in
            DetailSheet(sheet: sheet)
                .environmentObject(store)
                .presentationDetents([.height(530), .large])
                .presentationDragIndicator(.visible)

        }
        .alert("Calls unavailable in demo", isPresented: Binding(get: { store.errorMessage != nil }, set: { if !$0 { store.errorMessage = nil } })) {
            Button("OK", role: .cancel) { store.errorMessage = nil }
        } message: { Text(store.errorMessage ?? "") }
        .environment(\.dynamicTypeSize, store.largeText ? max(systemTextSize, .xxLarge) : systemTextSize)
        .preferredColorScheme(appearance == "light" ? .light : appearance == "dark" ? .dark : nil)
        .onReceive(clock) { now in
            if scenePhase == .active { store.tick(now: now) }
        }
        .onChange(of: scenePhase) { phase in
            if phase == .active { store.tick() }
        }
    }

    private var toolbar: some View {
        HStack {
            BrandWordmark()
                .scaledFont(size: 12, weight: .semibold)
                .foregroundStyle(Palette.accent)
            Spacer()
            Button { store.sheet = .demo } label: {
                Label("Demo", systemImage: "play.fill")
                    .scaledFont(size: 10)
                    .foregroundStyle(Palette.accent)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Palette.softAccent, in: Capsule())
                    .frame(minHeight: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Try an incoming demo call")
            .accessibilityIdentifier("demoButton")
        }
        .frame(height: 26)
    }

    private var tabBar: some View {
        HStack(spacing: 0) {
            ForEach(AppTab.allCases, id: \.self) { tab in
                Button { store.tab = tab } label: {
                    VStack(spacing: 4) {
                        Image(systemName: tab.symbol)
                            .scaledFont(size: 24, weight: store.tab == tab ? .semibold : .regular)
                        Text(tab.rawValue).font(.system(size: 11))
                    }
                    .foregroundStyle(store.tab == tab ? Palette.accent : Palette.secondary)
                    .frame(maxWidth: .infinity, minHeight: 50)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("tab\(tab.rawValue)")
                .accessibilityAddTraits(store.tab == tab ? .isSelected : [])
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 9)
        .padding(.bottom, 8)
        .background(Palette.surface.ignoresSafeArea(edges: .bottom))
        .overlay(alignment: .top) { Rectangle().fill(Palette.line).frame(height: 1) }
    }
}
