import SwiftUI

struct ProductionCallView: View {
    let call: PhoneCall
    @EnvironmentObject private var store: ProductionStore
    @State private var showingKeypad = false
    @State private var busy = false
    private let clock = Timer.publish(every: 1, on: .main, in: .common).autoconnect()
    @State private var now = Date()
    /// A service that cannot hold a call or send keypad tones (LiveKit) does not get buttons that can only fail.
    @MainActor private var offersHoldAndKeypad: Bool { store.coordinator.backend.supportsHoldAndKeypad }
    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                VStack(spacing: 4) {
                    Wordmark()
                    #if targetEnvironment(simulator)
                    Text("Simulator call test").font(.callout).foregroundStyle(Theme.textSecondary)
                    #endif
                }
                VStack(spacing: 8) {
                    Avatar(person: call.person, size: call.connectedAt == nil ? 104 : 80)
                    Text(call.person.name).font(.largeTitle.weight(.semibold)).foregroundStyle(Theme.textPrimary)
                        .lineLimit(2).minimumScaleFactor(0.7).accessibilityAddTraits(.isHeader)
                    if !call.person.number.isEmpty && call.person.number != call.person.name {
                        Text(call.person.number).font(.title3).foregroundStyle(Theme.textSecondary)
                    }
                    Text(status).font(.title3.weight(.medium)).monospacedDigit().foregroundStyle(Theme.textSecondary)
                }
                if call.connectedAt != nil {
                    VoiceStatusCard(voice: displayedVoice, heading: "Voice check", message: assessment) {
                        if let previous = call.lastDeepfakeResult,
                           let current = call.deepfake, [.waiting, .analyzing, .unavailable].contains(current.state) {
                            Text("Last result: \(previous.voice.label)").font(.callout.weight(.semibold))
                                .foregroundStyle(Theme.textPrimary)
                        }
                        Text("Not an identity check").font(.callout).foregroundStyle(Theme.textSecondary)
                    }
                    let text = call.transcript ?? TranscriptAssessment(state: .listening, updatedAt: now)
                    VStack(alignment: .leading, spacing: 10) {
                        Label("Scam-language check", systemImage: "text.bubble")
                            .font(.callout.weight(.semibold)).foregroundStyle(Theme.textSecondary)
                            .accessibilityAddTraits(.isHeader)
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Image(systemName: text.isWarning ? "exclamationmark.triangle.fill" : "text.magnifyingglass")
                                .accessibilityHidden(true)
                            Text(text.title).accessibilityIdentifier("transcriptAssessmentTitle")
                        }
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(text.isWarning ? Theme.statusAI : Theme.textPrimary)
                        Text(text.message).font(.body).foregroundStyle(Theme.textPrimary)
                            .accessibilityIdentifier("transcriptAssessmentScore")
                        Text("Based on the caller’s words. A low score does not prove a call is safe.")
                            .font(.callout).foregroundStyle(Theme.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .multilineTextAlignment(.leading)
                    .card(background: text.isWarning ? Theme.statusAIBackground : Theme.backgroundSurface,
                          border: text.isWarning ? Theme.statusAI : Theme.borderDecorative)
                }
            }
            .padding(.horizontal, 24).padding(.vertical, 16)
            .frame(maxWidth: 520).frame(maxWidth: .infinity)
        }
        .scrollIndicators(.hidden)
        .safeAreaInset(edge: .bottom, spacing: 0) { controls }
        .multilineTextAlignment(.center)
        .background(Theme.backgroundPrimary.ignoresSafeArea())
        .onReceive(clock) { now = $0 }
    }
    /// Answer and end controls stay pinned to the bottom so they are never scrolled out of reach.
    @ViewBuilder private var controls: some View {
        VStack(spacing: 16) {
            if call.stage == .incoming {
                Text("Callshield checks the voice after you answer.")
                    .font(.callout).foregroundStyle(Theme.textSecondary)
                HStack {
                    control("Decline", "phone.down.fill", style: .decline, size: 84) { try await store.coordinator.end() }
                    Spacer()
                    control("Accept", "phone.fill", style: .accept, size: 84) { try await store.coordinator.answer() }
                }.padding(.horizontal, 16)
            } else {
                if showingKeypad {
                    PhoneKeypad { digit in perform { try await store.coordinator.sendDTMF(digit) } }
                } else {
                    HStack(spacing: 20) {
                        control("Mute", call.muted ? "mic.slash.fill" : "mic.fill", style: .toggle(call.muted)) {
                            try await store.coordinator.setMuted(!call.muted)
                        }
                        control("Speaker", "speaker.wave.2.fill", style: .toggle(call.speaker)) {
                            try store.coordinator.setSpeaker(!call.speaker)
                        }
                        if offersHoldAndKeypad {
                            control(call.stage == .held ? "Resume" : "Hold", "pause.fill", style: .toggle(call.stage == .held)) {
                                try await store.coordinator.setHeld(call.stage != .held)
                            }
                        }
                    }.disabled(call.connectedAt == nil)
                }
                if offersHoldAndKeypad {
                    Button(showingKeypad ? "Hide keypad" : "Show keypad") { showingKeypad.toggle() }
                        .buttonStyle(ActionButtonStyle(kind: .secondary))
                        .disabled(call.connectedAt == nil)
                }
                Button { perform { try await store.coordinator.end() } } label: {
                    Label("End call", systemImage: "phone.down.fill")
                }
                .buttonStyle(ActionButtonStyle(kind: .destructive)).disabled(busy)
            }
        }
        .padding(.horizontal, 24).padding(.top, 12).padding(.bottom, 8)
        .frame(maxWidth: 520).frame(maxWidth: .infinity)
        .background(Theme.backgroundPrimary.ignoresSafeArea(edges: .bottom))
    }
    private var status: String {
        switch call.stage {
        case .incoming: return "Incoming call"
        case .connecting: return "Connecting…"
        case .held: return "On hold"
        case .connected: return callDuration(call.connectedAt.map { max(0, Int(now.timeIntervalSince($0))) } ?? 0)
        }
    }
    /// Waiting for enough speech is the start of a check, so it looks like Analyzing rather than an inconclusive result.
    private var displayedVoice: Voice { call.deepfake?.state == .waiting ? .analyzing : call.voice }
    private var assessment: String {
        if let deepfake = call.deepfake { return deepfake.message }
        switch call.voice {
        case .analyzing: return "Checking the caller’s voice…"
        case .ai: return "This voice may be AI-generated."
        case .human: return "This voice appears to be human."
        case .unknown: return "A voice assessment is not available."
        }
    }
    private func control(_ title: String, _ symbol: String, style: CallControlButton.Style, size: CGFloat = 76,
                         operation: @escaping () async throws -> Void) -> some View {
        CallControlButton(title: title, symbol: symbol, style: style, size: size) { perform(operation) }.disabled(busy)
    }
    private func perform(_ operation: @escaping () async throws -> Void) {
        guard !busy else { return }
        busy = true
        Task {
            defer { busy = false }
            do { try await operation() }
            catch { store.errorMessage = error.localizedDescription }
        }
    }
}


