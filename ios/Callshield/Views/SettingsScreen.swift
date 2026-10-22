import SwiftUI

struct SettingsScreen: View {
    @EnvironmentObject private var store: CallshieldStore
    @AppStorage(AppearanceChoice.storageKey) private var appearance = AppearanceChoice.system
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(spacing: 10) {
                BrandMark()
                Text("Callshield").font(.title2.weight(.semibold))
                Text("More clarity for every incoming call.")
                    .font(.body).foregroundStyle(Theme.textSecondary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)

            SectionHeader(text: "Display")
            DisplaySettings(largeText: $store.largeText, appearance: $appearance)

            SectionHeader(text: "Calling")
            GroupedRows {
                InfoRow(label: "Calling mode", value: "Incoming only")
                RowDivider()
                InfoRow(label: "Connection", value: "Demo")
            }

            SectionHeader(text: "Understanding voice labels")
            VoiceLabelGuide()

            Footnote(text: "This prototype uses sample calls and simulated results. Real incoming calls and voice analysis require connected services.",
                     symbol: "info.circle")
        }
    }
}
