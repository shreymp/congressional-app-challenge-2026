import SwiftUI

struct CallScreen: View {
    let call: ActiveCall
    @EnvironmentObject private var store: CallmaStore
    private var connected: Bool { call.stage == .connected }

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                HStack(spacing: 8) {
                    Wordmark()
                    Text("Demo").font(.subheadline.weight(.semibold))
                        .foregroundStyle(Theme.actionAccent)
                        .padding(.horizontal, 10).padding(.vertical, 4)
                        .background(Theme.actionAccentBackground, in: Capsule())
                }
                VStack(spacing: 8) {
                    Avatar(person: call.person, size: connected ? 80 : 104)
                    Text(call.person.name)
                        .font(.largeTitle.weight(.semibold))
                        .lineLimit(2).minimumScaleFactor(0.7)
                        .accessibilityAddTraits(.isHeader)
                    Text(call.person.number)
                        .font(.title3).foregroundStyle(Theme.textSecondary)
                    Text(connected ? callDuration(store.seconds) : "Incoming call")
                        .font(.title3.weight(.medium)).monospacedDigit()
                        .foregroundStyle(Theme.textSecondary)
                        .accessibilityIdentifier("callStatus")
                }
                if connected {
                    VoiceStatusCard(voice: call.voice, heading: "Voice check", message: assessmentText) {
                        Text("Simulated result · Not an identity check")
                            .font(.callout).foregroundStyle(Theme.textSecondary)
                    }
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier("activeVoiceLabel")
                }
            }
            .multilineTextAlignment(.center)
            .padding(.horizontal, 24)
            .padding(.vertical, 16)
            .frame(maxWidth: 520)
            .frame(maxWidth: .infinity)
        }
        .scrollIndicators(.hidden)
        // Answer and end controls stay pinned to the bottom so they are never scrolled out of reach.
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 12) {
                if connected { connectedActions } else { answerActions }
                Text("Simulated call · No audio is transmitted")
                    .font(.callout).foregroundStyle(Theme.textSecondary)
            }
            .padding(.horizontal, 24).padding(.top, 12).padding(.bottom, 8)
            .frame(maxWidth: 520).frame(maxWidth: .infinity)
            .background(Theme.backgroundPrimary.ignoresSafeArea(edges: .bottom))
        }
        .foregroundStyle(Theme.textPrimary)
        .background(Theme.backgroundPrimary.ignoresSafeArea())
        .accessibilityElement(children: .contain)
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
        VStack(spacing: 16) {
            Text("Callma checks the voice after you answer.")
                .font(.callout).foregroundStyle(Theme.textSecondary)
            HStack {
                CallControlButton(title: "Decline", symbol: "phone.down.fill", style: .decline, size: 84) { store.finishCall() }
                    .accessibilityIdentifier("declineCall")
                Spacer()
                CallControlButton(title: "Accept", symbol: "phone.fill", style: .accept, size: 84) { store.accept() }
                    .accessibilityIdentifier("acceptCall")
            }
            .padding(.horizontal, 16)
        }
    }

    private var connectedActions: some View {
        VStack(spacing: 20) {
            HStack(spacing: 32) {
                CallControlButton(title: "Mute", symbol: store.muted ? "mic.slash.fill" : "mic.fill",
                                  style: .toggle(store.muted)) { store.toggleMute() }
                    .accessibilityIdentifier("muteCall")
                CallControlButton(title: "Speaker", symbol: "speaker.wave.2.fill",
                                  style: .toggle(store.speaker)) { store.toggleSpeaker() }
                    .accessibilityIdentifier("speakerCall")
            }
            Button { store.finishCall() } label: {
                Label("End call", systemImage: "phone.down.fill")
            }
            .buttonStyle(ActionButtonStyle(kind: .destructive))
            .accessibilityLabel("End call")
            .accessibilityIdentifier("endCall")
        }
    }
}
