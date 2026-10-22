import SwiftUI

struct RecentsScreen: View {
    @EnvironmentObject private var store: CallshieldStore

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            FilterBar(selection: $store.filter)
            PhoneSearchField(text: $store.search, label: "Search recent calls",
                             placeholder: "Search name, number or label", identifier: "callSearch")
            SectionHeader(text: "Incoming calls")
            if store.visibleCalls.isEmpty {
                EmptyStateView(symbol: "magnifyingglass", title: "No calls found",
                               message: store.search.isEmpty ? "Your missed calls will appear here." : "Try another name, number, or voice label.")
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier("emptyCalls")
            } else {
                GroupedRows {
                    ForEach(Array(store.visibleCalls.enumerated()), id: \.element.id) { index, call in
                        if index > 0 { RowDivider(inset: 66) }
                        Button { store.sheet = .call(call) } label: { callRow(call) }
                            .buttonStyle(.plain)
                            .accessibilityElement(children: .ignore)
                            .accessibilityAddTraits(.isButton)
                            .accessibilityLabel("\(call.person.name), \(call.missed ? "missed" : "received"), \(call.voice.label), \(call.when), details")
                            .accessibilityIdentifier("callRow-\(call.id)")
                    }
                }
            }
            Footnote(text: "Sample history. Voice labels are estimates, not identity checks.", symbol: "info.circle")
        }
    }

    private func callRow(_ call: CallEntry) -> some View {
        PersonRow(person: call.person, nameColor: call.missed ? Theme.textDestructive : Theme.textPrimary, trailing: call.when) {
            Label(call.missed ? "Missed call" : "Incoming call", systemImage: "phone.arrow.down.left")
                .font(.callout)
                .foregroundStyle(call.missed ? Theme.textDestructive : Theme.textSecondary)
            // Missed calls are never analysed, so they carry no voice result.
            if !call.missed { VoiceBadge(voice: call.voice) }
        }
    }
}
