import SwiftUI

struct CallshieldRootView: View {
    @EnvironmentObject private var store: CallshieldStore
    @Environment(\.scenePhase) private var scenePhase
    private let clock = Timer.publish(every: 0.1, on: .main, in: .common).autoconnect()

    var body: some View {
        ZStack {
            if let call = store.active {
                CallScreen(call: call)
            } else {
                VStack(spacing: 0) {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 0) {
                            toolbar
                            Text(store.tab.rawValue)
                                .font(.system(size: 36, weight: .bold))
                                .tracking(-1.2)
                                .accessibilityAddTraits(.isHeader)
                                .padding(.top, 11)
                                .padding(.bottom, 19)
                            switch store.tab {
                            case .recents: RecentsScreen()
                            case .contacts: ContactsScreen()
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
                .background(Color.white.ignoresSafeArea())
                .foregroundStyle(Palette.ink)
            }
        }
        .overlay(alignment: .bottom) {
            if !store.notice.isEmpty {
                Label(store.notice, systemImage: "checkmark")
                    .font(.system(size: 11))
                    .foregroundStyle(.white)
                    .padding(12)
                    .frame(maxWidth: .infinity)
                    .background(Color(hex: 0x284B3D), in: RoundedRectangle(cornerRadius: 12))
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
                .preferredColorScheme(.light)
        }
        .preferredColorScheme(store.active == nil ? .light : .dark)
        .onReceive(clock) { now in
            if scenePhase == .active { store.tick(now: now) }
        }
        .onChange(of: scenePhase) { phase in
            if phase == .active { store.tick() }
        }
    }

    private var toolbar: some View {
        HStack {
            Label("Callshield", systemImage: "checkmark.shield")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Color(hex: 0x327459))
            Spacer()
            Button { store.sheet = .demo } label: {
                Label("Demo", systemImage: "play.fill")
                    .font(.system(size: 10))
                    .foregroundStyle(Color(hex: 0x6C7D72))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color(hex: 0xF0F5F1), in: Capsule())
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
                        Image(systemName: tab == .recents ? "clock" : tab == .contacts ? "person.2" : "gearshape")
                            .font(.system(size: 24, weight: store.tab == tab ? .semibold : .regular))
                        Text(tab.rawValue).font(.system(size: 9))
                    }
                    .foregroundStyle(store.tab == tab ? Palette.green : Color(hex: 0xA1A4A9))
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
        .background(Color(hex: 0xFAFAFB).ignoresSafeArea(edges: .bottom))
        .overlay(alignment: .top) { Rectangle().fill(Color(hex: 0xEDEDEE)).frame(height: 1) }
    }
}
