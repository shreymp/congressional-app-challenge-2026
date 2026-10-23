import SwiftUI

struct DetailSheet: View {
    let sheet: AppSheet
    @EnvironmentObject private var store: CallshieldStore
    @Environment(\.dismiss) private var dismiss
    @State private var showUnavailable = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    Button { dismiss() } label: {
                        Label("Done", systemImage: "chevron.left")
                            .scaledFont(size: 13)
                            .frame(minHeight: 44)
                    }
                    .buttonStyle(.plain)
                    .keyboardShortcut(.cancelAction)
                    .foregroundStyle(Palette.accent)
                    .accessibilityIdentifier("sheetDone")
                    Spacer()
                    Text(isDemo ? "DEMO CALL" : "CALL DETAILS")
                        .scaledFont(size: 9).tracking(1.2)
                        .foregroundStyle(Palette.secondary)
                }
                .padding(.bottom, 23)
                switch sheet {
                case .demo: demoPicker
                case .call(let entry): detail(person: entry.person, entry: entry)
                case .contact(let person): detail(person: person, entry: nil)
                }
            }
            .padding(.horizontal, 23)
            .padding(.top, 21)
            .padding(.bottom, 25)
            .frame(maxWidth: 500)
            .frame(maxWidth: .infinity)
        }
        .alert("Calls unavailable in demo", isPresented: $showUnavailable) {
            Button("OK", role: .cancel) { }
        } message: { Text("This is an interactive demo. No call was placed. Use Demo to try a simulated incoming call.") }
        .background(Palette.surface)
        .foregroundStyle(Palette.ink)
    }

    private var isDemo: Bool { if case .demo = sheet { return true }; return false }

    private var demoPicker: some View {
        VStack(alignment: .leading, spacing: 0) {
            title("Try an incoming call")
            Text("Choose a simulated caller to preview the experience. No actual call will be placed.")
                .scaledFont(size: 12).foregroundStyle(Palette.secondary)
                .lineSpacing(5).fixedSize(horizontal: false, vertical: true)
            VStack(spacing: 0) {
                ForEach(Array(SampleData.demoPeople.enumerated()), id: \.element.id) { index, person in
                    Button { store.startCall(person) } label: {
                        HStack(spacing: 13) {
                            Avatar(person: person, icon: index == 0 ? "person" : index == 1 ? "cpu" : "waveform")
                            VStack(alignment: .leading, spacing: 5) {
                                Text(index == 0 ? "Human voice" : index == 1 ? "AI voice" : "Uncertain voice")
                                    .scaledFont(size: 13, weight: .semibold)
                                Text("\(person.name) · Simulated")
                                    .scaledFont(size: 11).foregroundStyle(Palette.secondary)
                            }
                            Spacer()
                            Image(systemName: "chevron.right").foregroundStyle(Palette.secondary)
                        }
                        .padding(.vertical, 16)
                        .contentShape(Rectangle())
                        .overlay(alignment: .bottom) { Rectangle().fill(Palette.line).frame(height: 1) }
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("demoCaller-\(person.voice.rawValue)")
                }
            }
            .padding(.vertical, 18)
            note("Unanswered demo calls move to Recents after 30 seconds.")
        }
    }

    private func detail(person: Person, entry: CallEntry?) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Avatar(person: person, size: 64, literalInitials: true).padding(.bottom, 18)
            title(person.name)
            Text(person.number).scaledFont(size: 14).foregroundStyle(Palette.secondary)
            HStack {
                Button { showUnavailable = true } label: { Label("Call", systemImage: "phone.fill") }
                    .accessibilityIdentifier("demoContactCall")
                Button { store.toggleFavorite(person) } label: {
                    Label(store.favoriteNumbers.contains(person.number) ? "Remove from Favorites" : "Add to Favorites", systemImage: "star")
                }.accessibilityIdentifier("demoFavoriteToggle")
            }.buttonStyle(.bordered).tint(Palette.accent).padding(.top, 18)
            if let entry {
                VStack(alignment: .leading, spacing: 7) {
                    HStack {
                        VoiceBadge(voice: entry.voice, size: 12)
                        ResultHelpButton(title: entry.voice.label, message: entry.voice.explanation)
                    }
                    if let risk = entry.scamRisk {
                        Text("Highest scam risk this call: \(risk)% · Simulated").font(.caption)
                    }
                    Text("Simulated voice assessment").scaledFont(size: 10).foregroundStyle(Palette.secondary)
                }
                .padding(.vertical, 24)
                VStack(spacing: 0) {
                    detailRow("Call type", value: entry.missed ? "Missed incoming call" : "Incoming call")
                    Divider()
                    detailRow("Time", value: entry.when)
                    Divider()
                    detailRow("Duration", value: entry.missed ? "Not answered" : callDuration(entry.duration))
                }
                .padding(.vertical, 4).padding(.horizontal, 13)
                .background(Palette.softAccent, in: RoundedRectangle(cornerRadius: 12))
                note("Voice classification does not verify identity or determine whether a caller is trustworthy.")
            } else {
                note("Sample contact. Changes stay in this demo session.")
            }
        }
    }

    private func title(_ text: String) -> some View {
        Text(text).scaledFont(size: 23, weight: .semibold).tracking(-0.6)
            .accessibilityAddTraits(.isHeader).padding(.bottom, 12)
    }
    private func note(_ text: String) -> some View {
        Text(text).scaledFont(size: 10).foregroundStyle(Palette.secondary)
            .lineSpacing(5).fixedSize(horizontal: false, vertical: true).padding(.top, 22)
    }
    private func detailRow(_ label: String, value: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(label).foregroundStyle(Palette.secondary)
            Spacer()
            Text(value).fontWeight(.medium).multilineTextAlignment(.trailing)
        }
        .scaledFont(size: 11).padding(.vertical, 12)
    }
}
