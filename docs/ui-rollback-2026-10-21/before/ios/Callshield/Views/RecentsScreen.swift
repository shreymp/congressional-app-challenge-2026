import SwiftUI

struct RecentsScreen: View {
    @EnvironmentObject private var store: CallshieldStore
    @ScaledMetric private var nameSize: CGFloat = 15
    @ScaledMetric(relativeTo: .caption) private var captionSize: CGFloat = 11
    @FocusState private var searchFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 0) {
                ForEach(CallFilter.allCases, id: \.self) { filter in
                    Button { store.filter = filter } label: {
                        Text(filter.rawValue)
                            .scaledFont(size: 12, weight: .semibold)
                            .frame(maxWidth: .infinity, minHeight: 27)
                            .background(store.filter == filter ? Color.white : .clear,
                                        in: RoundedRectangle(cornerRadius: 7))
                            .shadow(color: .black.opacity(store.filter == filter ? 0.1 : 0), radius: 2, y: 1)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("filter\(filter.rawValue)")
                    .accessibilityAddTraits(store.filter == filter ? .isSelected : [])
                }
            }
            .padding(3)
            .background(Palette.softAccent, in: RoundedRectangle(cornerRadius: 9))
            .padding(.bottom, 14)

            HStack(spacing: 7) {
                Image(systemName: "magnifyingglass").scaledFont(size: 18)
                TextField("Search", text: $store.search)
                    .scaledFont(size: 14)
                    .foregroundStyle(Palette.ink)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .focused($searchFocused)
                    .submitLabel(.search)
                    .onSubmit { searchFocused = false }
                    .accessibilityLabel("Search recent calls")
                    .accessibilityIdentifier("callSearch")
                if !store.search.isEmpty {
                    Button { store.search = "" } label: {
                        Image(systemName: "xmark").scaledFont(size: 15).frame(width: 30, height: 37)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Clear search")
                }
            }
            .foregroundStyle(Palette.secondary)
            .padding(.leading, 10)
            .padding(.trailing, 4)
            .frame(height: 37)
            .background(Palette.softAccent, in: RoundedRectangle(cornerRadius: 10))
            .padding(.bottom, 24)

            HStack {
                Text("INCOMING CALLS").tracking(1.1)
                Spacer()
                Text("Sample history")
            }
            .scaledFont(size: 9)
            .foregroundStyle(Palette.secondary)
            .padding(.bottom, 7)

            if store.visibleCalls.isEmpty {
                VStack(spacing: 10) {
                    Image(systemName: "magnifyingglass").scaledFont(size: 30)
                    Text("No calls found").scaledFont(size: 16, weight: .semibold)
                        .foregroundStyle(Color(hex: 0x34473C))
                    Text(store.search.isEmpty ? "Your missed calls will appear here." : "Try another name, number, or voice label.")
                        .scaledFont(size: 12).multilineTextAlignment(.center)
                }
                .foregroundStyle(Palette.secondary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 48)
                .accessibilityIdentifier("emptyCalls")
            } else {
                ForEach(store.visibleCalls) { call in
                    Button {
                        searchFocused = false
                        store.sheet = .call(call)
                    } label: { callRow(call) }
                    .buttonStyle(.plain)
                    .accessibilityElement(children: .ignore)
                    .accessibilityAddTraits(.isButton)
                    .accessibilityLabel("\(call.person.name), \(call.missed ? "missed" : "received"), \(call.voice.label), \(call.when), details")
                    .accessibilityIdentifier("callRow-\(call.id)")
                }
            }
            Footnote(text: "Voice labels are estimates, not identity verification.", shield: true)
        }
    }

    private func callRow(_ call: CallEntry) -> some View {
        HStack(spacing: 10) {
            Avatar(person: call.person)
            VStack(alignment: .leading, spacing: 5) {
                Text(call.person.name)
                    .scaledFont(size: nameSize + (store.largeText ? 2 : 0), weight: .semibold)
                    .tracking(-0.15)
                    .foregroundStyle(call.missed ? Palette.missed : Palette.ink)
                    .lineLimit(1)
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 3) {
                        Image(systemName: "arrow.down.left")
                        Text(call.missed ? "Missed" : "Incoming")
                        Text("·")
                        VoiceBadge(voice: call.voice, size: store.largeText ? 11 : 10)
                    }
                    VStack(alignment: .leading, spacing: 3) {
                        Label(call.missed ? "Missed" : "Incoming", systemImage: "arrow.down.left")
                        VoiceBadge(voice: call.voice, size: store.largeText ? 11 : 10)
                    }
                }
                .scaledFont(size: captionSize)
                .foregroundStyle(Palette.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if store.largeText {
                VStack(spacing: 5) { rowEnd(call) }
            } else {
                HStack(spacing: 7) { rowEnd(call) }
            }
        }
        .padding(.vertical, 16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .overlay(alignment: .bottom) { Rectangle().fill(Palette.line).frame(height: 1) }
    }

    @ViewBuilder private func rowEnd(_ call: CallEntry) -> some View {
        Text(call.when)
            .scaledFont(size: 10)
            .foregroundStyle(Palette.secondary)
            .fixedSize()
        Image(systemName: "info.circle")
            .scaledFont(size: 17)
            .foregroundStyle(Color(hex: 0x528FCB))
    }
}
