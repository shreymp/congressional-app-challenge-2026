import SwiftUI

struct DetailSheet: View {
    let sheet: AppSheet
    @EnvironmentObject private var store: CallmaStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text(isDemo ? "Demo call" : "Details")
                        .font(.headline).foregroundStyle(Theme.textSecondary)
                    Spacer()
                    Button { dismiss() } label: {
                        Text("Done").font(.body.weight(.semibold))
                            .padding(.horizontal, 18).frame(minHeight: 44)
                            .background(Theme.backgroundSurface, in: Capsule())
                            .overlay(Capsule().strokeBorder(Theme.borderInteractive, lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                    .keyboardShortcut(.cancelAction)
                    .foregroundStyle(Theme.textPrimary)
                    .accessibilityIdentifier("sheetDone")
                }
                switch sheet {
                case .demo: demoPicker
                case .call(let entry): detail(person: entry.person, entry: entry)
                case .contact(let person): detail(person: person, entry: nil)
                }
            }
            .padding(.horizontal, Theme.margin)
            .padding(.top, 24)
            .padding(.bottom, 32)
            .frame(maxWidth: 520)
            .frame(maxWidth: .infinity)
        }
        .background(Theme.backgroundPrimary.ignoresSafeArea())
        .foregroundStyle(Theme.textPrimary)
    }

    private var isDemo: Bool { if case .demo = sheet { return true }; return false }

    private var demoPicker: some View {
        VStack(alignment: .leading, spacing: 16) {
            title("Try an incoming call")
            Text("Choose a pretend caller to see how Callma works. No real call is made.")
                .font(.body).foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            GroupedRows {
                ForEach(Array(SampleData.demoPeople.enumerated()), id: \.element.id) { index, person in
                    if index > 0 { RowDivider(inset: 66) }
                    let voice = person.voice
                    Button { store.startCall(person) } label: {
                        HStack(spacing: 14) {
                            Image(systemName: voice.symbol)
                                .font(.system(size: 22, weight: .semibold))
                                .foregroundStyle(voice.foreground)
                                .frame(width: 52, height: 52)
                                .background(voice.background, in: Circle())
                                .accessibilityHidden(true)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(index == 0 ? "Human voice" : index == 1 ? "AI voice" : "Uncertain voice")
                                    .font(.body.weight(.semibold))
                                Text("\(person.name) · Pretend call")
                                    .font(.callout).foregroundStyle(Theme.textSecondary)
                            }
                            Spacer()
                            Image(systemName: "chevron.right").font(.body.weight(.semibold))
                                .foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
                        }
                        .padding(.vertical, 14)
                        .frame(minHeight: 76)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("demoCaller-\(person.voice.rawValue)")
                }
            }
            Footnote(text: "If you don’t answer within 30 seconds, the demo call moves to Recents as missed.", symbol: "clock")
        }
    }

    private func detail(person: Person, entry: CallEntry?) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 16) {
                Avatar(person: person, size: 72, literalInitials: true)
                VStack(alignment: .leading, spacing: 4) {
                    title(person.name)
                    Text(person.number).font(.title3).foregroundStyle(Theme.textSecondary)
                }
            }
            if let entry {
                VoiceStatusCard(voice: entry.voice, heading: "Voice check",
                                message: entry.missed ? "This call wasn’t answered, so the voice wasn’t checked." : entry.voice.explanation) {
                    Text("Simulated result").font(.callout).foregroundStyle(Theme.textSecondary)
                }
                SectionHeader(text: "Call information")
                GroupedRows {
                    InfoRow(label: "Call type", value: entry.missed ? "Missed incoming call" : "Incoming call")
                    RowDivider()
                    InfoRow(label: "Time", value: entry.when)
                    RowDivider()
                    InfoRow(label: "Duration", value: entry.missed ? "Not answered" : callDuration(entry.duration))
                }
                Footnote(text: "Voice classification does not verify identity or determine whether a caller is trustworthy.", symbol: "info.circle")
            } else {
                Footnote(text: "Sample contact for incoming caller identification. Outgoing calls are not available.")
            }
        }
    }

    private func title(_ text: String) -> some View {
        Text(text).font(.title.weight(.semibold))
            .accessibilityAddTraits(.isHeader)
            .fixedSize(horizontal: false, vertical: true)
    }
}
