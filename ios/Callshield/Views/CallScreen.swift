import SwiftUI

struct CallScreen: View {
    let call: ActiveCall
    @EnvironmentObject private var store: CallshieldStore
    private var connected: Bool { call.stage == .connected }

    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 0) {
                    HStack(spacing: 6) {
                        BrandWordmark(onDark: true)
                            .scaledFont(size: 12)
                        Text("DEMO").scaledFont(size: 8).tracking(1)
                            .padding(.horizontal, 5).padding(.vertical, 2)
                            .overlay(RoundedRectangle(cornerRadius: 4).stroke(.white.opacity(0.15)))
                    }
                    .foregroundStyle(Color(hex: 0xD3DFD7))
                    Avatar(person: call.person, size: connected ? 70 : 90)
                        .padding(.top, connected ? 17 : 29)
                        .padding(.bottom, connected ? 14 : 20)
                    Text(call.person.name)
                        .scaledFont(size: 29, weight: .medium).tracking(-0.7)
                        .accessibilityAddTraits(.isHeader)
                    Text(call.person.number)
                        .scaledFont(size: 14).foregroundStyle(Color(hex: 0xBDCCC3))
                        .padding(.top, 9).padding(.bottom, 5)
                    Text(connected ? callDuration(store.seconds) : "Incoming call")
                        .scaledFont(size: 14).monospacedDigit()
                        .foregroundStyle(Color(hex: 0xD5E4FB))
                        .accessibilityIdentifier("callStatus")
                    if connected {
                        VStack(spacing: 0) {
                            Text("Caller’s voice").font(.caption.weight(.semibold))
                            HStack(spacing: 4) {
                                VoiceBadge(voice: call.voice, size: 13, onCall: true)
                                    .accessibilityIdentifier("activeVoiceLabel")
                                ResultHelpButton(title: call.voice.label, message: call.voice.explanation, onDark: true)
                            }
                            Text(assessmentText)
                                .scaledFont(size: 12).foregroundStyle(Color(hex: 0xD0DCD5))
                                .padding(.top, 12).padding(.bottom, 7)
                            Text("Simulated result · Not an identity check")
                                .scaledFont(size: 9).foregroundStyle(Color(hex: 0xD5E4FB))
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14).padding(.horizontal, 10)
                        .background(.white.opacity(0.03), in: RoundedRectangle(cornerRadius: 18))
                        .overlay(RoundedRectangle(cornerRadius: 18).stroke(.white.opacity(0.09)))
                        .padding(.top, 18)
                    }
                    if connected {
                        VStack(spacing: 8) {
                            Text("Scam warning").font(.caption.weight(.semibold))
                            Text(call.scamRisk.map { $0 >= 70 ? "Possible scam language" : "No strong scam signal" } ?? "Listening…")
                                .font(.subheadline.weight(.semibold))
                            Text(call.scamRisk.map { "Highest scam risk this call: \($0)%" } ?? "Waiting for the simulated caller’s words.")
                                .font(.caption)
                            Text("Simulated result · A low score does not prove a call is safe.").font(.caption2)
                        }.padding(14).frame(maxWidth: .infinity)
                            .background(.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 18))
                            .padding(.top, 12)
                    }
                    Spacer(minLength: 20)
                    if connected { connectedActions } else { answerActions }
                    Text("Simulated call · No audio is transmitted")
                        .scaledFont(size: 9).foregroundStyle(Color(hex: 0xD5E4FB))
                        .padding(.top, connected ? 13 : 27)
                        .padding(.bottom, 4)
                }
                .multilineTextAlignment(.center)
                .padding(.horizontal, 28)
                .padding(.top, 9)
                .padding(.bottom, 25)
                .frame(maxWidth: 500)
                .frame(minHeight: geometry.size.height)
                .frame(maxWidth: .infinity)
            }
            .scrollIndicators(.hidden)
        }
        .foregroundStyle(.white)
        .background {
            RadialGradient(colors: [Color(hex: 0x195ED9), Color(hex: 0x274FA0), Color(hex: 0x152654)],
                           center: .init(x: 0.2, y: 0.2), startRadius: 0, endRadius: 700)
                .ignoresSafeArea()
        }
        .accessibilityIdentifier(connected ? "activeCallScreen" : "incomingCallScreen")
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
        VStack(spacing: 24) {
            HStack(spacing: 43) {
                roundButton(store.muted ? "unmute" : "mute", symbol: store.muted ? "mic.slash" : "mic",
                            size: 59, color: store.muted ? .white : .white.opacity(0.13),
                            foreground: store.muted ? Color(hex: 0x273C31) : .white,
                            id: "muteCall") { store.toggleMute() }
                    .accessibilityValue(store.muted ? "On" : "Off")
                roundButton("speaker", symbol: "speaker.wave.2", size: 59,
                            color: store.speaker ? .white : .white.opacity(0.13),
                            foreground: store.speaker ? Color(hex: 0x273C31) : .white,
                            id: "speakerCall") { store.toggleSpeaker() }
                    .accessibilityValue(store.speaker ? "On" : "Off")
            }
            Button { store.finishCall() } label: {
                Image(systemName: "phone.down.fill").scaledFont(size: 30)
                    .frame(width: 64, height: 64)
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
                Text(label).scaledFont(size: 12)
            }
        }
        .buttonStyle(CallActionStyle())
        .accessibilityIdentifier(id)
    }
}
