import SwiftUI

struct ContactsScreen: View {
    @EnvironmentObject private var store: CallshieldStore
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Familiar faces. Incoming calls only.")
                .font(.system(size: 12))
                .foregroundStyle(Palette.secondary)
                .padding(.bottom, 25)
            ForEach(SampleData.contacts) { person in
                Button { store.sheet = .contact(person) } label: {
                    HStack(spacing: 13) {
                        Avatar(person: person)
                        VStack(alignment: .leading, spacing: 5) {
                            Text(person.name).font(.system(size: 13, weight: .semibold))
                            Text(person.number).font(.system(size: 11)).foregroundStyle(Color(hex: 0x999999))
                        }
                        Spacer()
                        Image(systemName: "chevron.right").font(.system(size: 18)).foregroundStyle(Color(hex: 0xAAAAAA))
                    }
                    .padding(.vertical, 16)
                    .contentShape(Rectangle())
                    .overlay(alignment: .bottom) { Rectangle().fill(Palette.line).frame(height: 1) }
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("contact-\(person.initials)")
                .accessibilityLabel("\(person.name), \(person.number), contact details")
            }
            Footnote(text: "Demo contacts · No address book access")
        }
    }
}
