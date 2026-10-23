import SwiftUI

struct CallScreen: View {
    let call: ActiveCall
    @EnvironmentObject private var store: CallshieldStore
    private var connected: Bool { call.stage == .connected }

    @Environment(\.dynamicTypeSize) private var textSize
    @State private var showingDetails = false
    @State private var wordsDetails = false

    var body: some View {
        VStack(spacing: 14) {
            Text("callma. Demo").font(.caption).foregroundStyle(Palette.secondary)
            Spacer(minLength: 0)
            if !textSize.isAccessibilitySize { Avatar(person: call.person, size: 76) }
            Text(call.person.name).font(.title.weight(.semibold)).lineLimit(2)
                .accessibilityAddTraits(.isHeader)
            if !textSize.isAccessibilitySize { Text(call.person.number).font(.body).foregroundStyle(Palette.secondary) }
            Text(connected ? callDuration(store.seconds) : "Incoming call")
                .font(.caption).monospacedDigit().foregroundStyle(Palette.secondary)
                .accessibilityIdentifier("callStatus")
            if connected {
                VStack(spacing: 0) {
                    Button { wordsDetails = false; showingDetails.toggle() } label: {
                        HStack {
                            Text("Voice").font(.caption)
                            Spacer()
                            VoiceBadge(voice: call.voice, size: 13).accessibilityIdentifier("activeVoiceLabel")
                            Image(systemName: "chevron.down").font(.caption2)
                        }.frame(minHeight: 44).contentShape(Rectangle())
                    }.buttonStyle(.plain).accessibilityIdentifier("demoVoiceDetails")
                    Text(assessmentText).font(.caption).foregroundStyle(Palette.secondary).lineLimit(2)
                    Divider().padding(.vertical, 8)
                    Button { wordsDetails = true; showingDetails.toggle() } label: {
                        HStack {
                            Text("Words").font(.caption)
                            Spacer()
                            Text(call.scamRisk.map { "\($0)/100" } ?? "Listening…").font(.subheadline.weight(.semibold))
                            Image(systemName: "chevron.down").font(.caption2)
                        }.frame(minHeight: 44).contentShape(Rectangle())
                    }.buttonStyle(.plain).accessibilityIdentifier("demoWordDetails")
                }.padding(14).background(Palette.surface, in: RoundedRectangle(cornerRadius: 18))
                .overlay(alignment: .top) {
                    if showingDetails {
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Text(wordsDetails ? "Caller’s words" : "Caller’s voice").font(.headline)
                                Spacer()
                                Button { showingDetails = false } label: { Image(systemName: "xmark").frame(width: 44, height: 44) }
                                    .accessibilityLabel("Close details")
                            }
                            ScrollView {
                                Text(wordsDetails
                                    ? "Simulated transcript score: \(call.scamRisk.map(String.init) ?? "unavailable") out of 100. A low score does not prove a call is safe."
                                    : call.voice.explanation).font(.body)
                            }.frame(maxHeight: 200)
                            Text("Simulated result · Not an identity check").font(.caption).foregroundStyle(Palette.secondary)
                        }.padding(18).background(Palette.surface, in: RoundedRectangle(cornerRadius: 20))
                            .overlay(RoundedRectangle(cornerRadius: 20).stroke(Palette.line))
                            .shadow(color: .black.opacity(0.18), radius: 18, y: 6)
                            .offset(y: 48).zIndex(1)
                    }
                }.zIndex(1)
            }
            Spacer(minLength: 8)
            if connected { connectedActions } else { answerActions }
            Text("Simulated call · No audio is transmitted").font(.caption2).foregroundStyle(Palette.secondary)
        }
        .multilineTextAlignment(.center)
        .padding(.horizontal, 24).padding(.vertical, 16)
        .frame(maxWidth: 500).frame(maxWidth: .infinity)
        .foregroundStyle(Palette.ink)
        .background {
            LinearGradient(colors: [Color(hex: 0x2B3545), Color(hex: 0x111721)], startPoint: .topLeading, endPoint: .bottomTrailing)
                .ignoresSafeArea()
        }
        .preferredColorScheme(.dark)
    }

    private var assessmentText: String {
        switch call.voice {
        case .analyzing: return "Checking the simulated voice…"
        case .ai: return "This voice may be AI-generated."
        case .human: return "This voice appears to be human."
        case .unknown: return "There isn’t enough information to tell."
        }
    }

    private var answerActions: some View {
        HStack {
            roundButton("Decline", symbol: "phone.down.fill", size: 70,
                        color: Palette.coral, id: "declineCall") { store.finishCall() }
            Spacer()
            roundButton("Accept", symbol: "phone.fill", size: 70,
                        color: Palette.teal, id: "acceptCall") { store.accept() }
        }
        .padding(.horizontal, 12)
    }

    private var connectedActions: some View {
        VStack(spacing: 18) {
            HStack(spacing: 32) {
                roundButton(store.muted ? "unmute" : "mute", symbol: store.muted ? "mic.slash" : "mic",
                            size: 59, color: store.muted ? Palette.ink : Palette.softAccent,
                            foreground: store.muted ? Palette.surface : Palette.ink,
                            id: "muteCall") { store.toggleMute() }
                    .accessibilityValue(store.muted ? "On" : "Off")
                roundButton("speaker", symbol: "speaker.wave.2", size: 59,
                            color: store.speaker ? Palette.ink : Palette.softAccent,
                            foreground: store.speaker ? Palette.surface : Palette.ink,
                            id: "speakerCall") { store.toggleSpeaker() }
                    .accessibilityValue(store.speaker ? "On" : "Off")
            }
            Button { store.finishCall() } label: {
                Image(systemName: "phone.down.fill").scaledFont(size: 30)
                    .foregroundStyle(.white).frame(width: 80, height: 80)
                    .background(Palette.coral, in: Circle())
            }
            .buttonStyle(CallActionStyle())
            .accessibilityLabel("End call")
            .accessibilityIdentifier("endCall")
        }
    }

    private func roundButton(_ label: String, symbol: String, size: CGFloat, color: Color,
                             foreground: Color = .white, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 10) {
                Image(systemName: symbol).scaledFont(size: 29)
                    .foregroundStyle(foreground)
                    .frame(width: size, height: size).background(color, in: Circle())
                Text(label.capitalized).font(.caption).lineLimit(1)
            }
        }
        .buttonStyle(CallActionStyle())
        .accessibilityIdentifier(id)
    }
}
