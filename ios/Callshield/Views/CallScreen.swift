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
                            .font(.system(size: 12))
                        Text("DEMO").font(.system(size: 8)).tracking(1)
                            .padding(.horizontal, 5).padding(.vertical, 2)
                            .overlay(RoundedRectangle(cornerRadius: 4).stroke(Palette.line))
                    }
                    .foregroundStyle(Palette.secondary)
                    Avatar(person: call.person, size: connected ? 70 : 90)
                        .padding(.top, connected ? 17 : 29)
                        .padding(.bottom, connected ? 14 : 20)
                    Text(call.person.name)
                        .font(.system(size: 29, weight: .medium)).tracking(-0.7)
                        .accessibilityAddTraits(.isHeader)
                    Text(call.person.number)
                        .font(.system(size: 14)).foregroundStyle(Palette.secondary)
                        .padding(.top, 9).padding(.bottom, 5)
                    Text(connected ? callDuration(store.seconds) : "Incoming call")
                        .font(.system(size: 14)).monospacedDigit()
                        .foregroundStyle(Palette.secondary)
                        .accessibilityIdentifier("callStatus")
                    if connected {
                        VStack(spacing: 0) {
                            VoiceBadge(voice: call.voice, size: 13, onCall: true)
                                .accessibilityIdentifier("activeVoiceLabel")
                            Text(assessmentText)
                                .font(.system(size: 12)).foregroundStyle(Palette.secondary)
                                .padding(.top, 12).padding(.bottom, 7)
                            Text("Simulated result · Not an identity check")
                                .font(.system(size: 9)).foregroundStyle(Palette.secondary)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14).padding(.horizontal, 10)
                        .background(Palette.surface, in: RoundedRectangle(cornerRadius: 18))
                        .overlay(RoundedRectangle(cornerRadius: 18).stroke(Palette.line))
                        .padding(.top, 18)
                    }
                    Spacer(minLength: 20)
                    if connected { connectedActions } else { answerActions }
                    Text("Simulated call · No audio is transmitted")
                        .font(.system(size: 9)).foregroundStyle(Palette.secondary)
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
        .foregroundStyle(Palette.ink)
        .background {
            RadialGradient(colors: [Palette.softAccent, Palette.surface, Palette.canvas],
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
                        color: Palette.destructive, foreground: .white, id: "declineCall") { store.finishCall() }
            Spacer()
            roundButton("Accept", symbol: "phone.fill", size: 70,
                        color: Palette.action, foreground: Palette.actionInk, id: "acceptCall") { store.accept() }
        }
        .padding(.horizontal, 12)
    }

    private var connectedActions: some View {
        VStack(spacing: 24) {
            HStack(spacing: 43) {
                roundButton(store.muted ? "unmute" : "mute", symbol: store.muted ? "mic.slash" : "mic",
                            size: 59, color: store.muted ? Palette.action : Palette.softAccent,
                            foreground: store.muted ? Palette.actionInk : Palette.ink,
                            id: "muteCall") { store.toggleMute() }
                    .accessibilityValue(store.muted ? "On" : "Off")
                roundButton("speaker", symbol: "speaker.wave.2", size: 59,
                            color: store.speaker ? Palette.action : Palette.softAccent,
                            foreground: store.speaker ? Palette.actionInk : Palette.ink,
                            id: "speakerCall") { store.toggleSpeaker() }
                    .accessibilityValue(store.speaker ? "On" : "Off")
            }
            Button { store.finishCall() } label: {
                Image(systemName: "phone.down.fill").font(.system(size: 30)).foregroundStyle(.white)
                    .frame(width: 64, height: 64)
                    .background(Palette.destructive, in: Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("End call")
            .accessibilityIdentifier("endCall")
        }
    }

    private func roundButton(_ label: String, symbol: String, size: CGFloat, color: Color,
                             foreground: Color = Palette.ink, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 10) {
                Image(systemName: symbol).font(.system(size: 29))
                    .foregroundStyle(foreground)
                    .frame(width: size, height: size).background(color, in: Circle())
                Text(label).font(.system(size: 12))
            }
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(id)
    }
}
