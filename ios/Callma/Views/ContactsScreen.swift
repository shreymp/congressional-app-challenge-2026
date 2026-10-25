import SwiftUI

struct ContactsScreen: View {
    @EnvironmentObject private var store: CallmaStore
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Choose a contact to view details.")
                .scaledFont(size: 12)
                .foregroundStyle(Palette.secondary)
                .padding(.bottom, 25)
            ForEach(SampleData.contacts) { person in
                Button { store.sheet = .contact(person) } label: {
                    HStack(spacing: 13) {
                        Avatar(person: person)
                        VStack(alignment: .leading, spacing: 5) {
                            Text(person.name).scaledFont(size: 13, weight: .semibold)
                            Text(person.number).scaledFont(size: 11).foregroundStyle(Palette.secondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right").scaledFont(size: 18).foregroundStyle(Palette.secondary)
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

struct DemoFavoritesScreen: View {
    @EnvironmentObject private var store: CallmaStore
    var body: some View {
        if store.favorites.isEmpty {
            PhoneEmptyView(symbol: "star", title: "No favorites", message: "Open a contact and tap Add to Favorites.")
            Button("Open Contacts") { store.tab = .contacts }.tint(Palette.accent)
                .frame(maxWidth: .infinity)
        } else {
            ForEach(store.favorites) { person in
                ProductionContactRow(person: person) { store.sheet = .contact(person) }
                    .accessibilityIdentifier("favorite-\(person.initials)")
            }
        }
    }
}

struct DemoKeypadScreen: View {
    @EnvironmentObject private var store: CallmaStore
    @FocusState private var editing: Bool
    var body: some View {
        VStack(spacing: 16) {
            TextField("Enter a number", text: $store.dialedNumber)
                .scaledFont(size: 30).multilineTextAlignment(.center)
                .keyboardType(.phonePad).focused($editing)
                .accessibilityLabel("Phone number").accessibilityIdentifier("demoNumber")
                .padding(.top, 12)
            if editing { Button("Done") { editing = false }.tint(Palette.accent) }
            PhoneKeypad { digit in editing = false; store.dialedNumber.append(digit) }
            HStack {
                Button { editing = false; if store.dialedNumber.isEmpty { store.dialedNumber = "+" } } label: {
                    Image(systemName: "plus").frame(width: 60, height: 60)
                }.foregroundStyle(Palette.secondary).accessibilityLabel("International prefix")
                Spacer()
                Button { editing = false; store.previewOutgoing(store.dialedNumber) } label: {
                    Image(systemName: "phone.fill").scaledFont(size: 29).foregroundStyle(Palette.actionInk)
                        .frame(width: 70, height: 70).background(Palette.action, in: Circle())
                }.buttonStyle(CallActionStyle()).disabled(store.dialedNumber.isEmpty)
                    .accessibilityLabel("Call").accessibilityIdentifier("demoCallButton")
                Spacer()
                Button { if !store.dialedNumber.isEmpty { store.dialedNumber.removeLast() } } label: {
                    Image(systemName: "delete.left").scaledFont(size: 23).frame(width: 60, height: 60)
                }.foregroundStyle(Palette.secondary).accessibilityLabel("Delete digit")
            }.frame(maxWidth: 290)
            Text("Demo only · outgoing calls are unavailable.").font(.caption).foregroundStyle(Palette.secondary)
        }.frame(maxWidth: .infinity).padding(.bottom, 24)
    }
}
