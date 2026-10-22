import SwiftUI

struct ContactsScreen: View {
    @EnvironmentObject private var store: CallmaStore
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Familiar faces. Incoming calls only.")
                .font(.body)
                .foregroundStyle(Theme.textSecondary)
            GroupedRows {
                ForEach(Array(SampleData.contacts.enumerated()), id: \.element.id) { index, person in
                    if index > 0 { RowDivider(inset: 66) }
                    Button { store.sheet = .contact(person) } label: {
                        PersonRow(person: person) {
                            Text(person.number).font(.callout).foregroundStyle(Theme.textSecondary)
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("contact-\(person.initials)")
                    .accessibilityLabel("\(person.name), \(person.number), contact details")
                }
            }
            Footnote(text: "Demo contacts. Callma does not read your address book in demo mode.", symbol: "lock.fill")
        }
    }
}
