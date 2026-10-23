import SwiftUI

struct ProductionCallView: View {
    let call: PhoneCall
    @EnvironmentObject private var store: ProductionStore
    @Environment(\.scenePhase) private var scenePhase
    @State private var showingGuardian = false
    @State private var leftDuringHighRisk = false
    @State private var departureWarningShown = false
    @State private var showingDepartureWarning = false
    @State private var showingKeypad = false
    @State private var busy = false
    private let clock = Timer.publish(every: 1, on: .main, in: .common).autoconnect()
    @State private var now = Date()
    /// A service that cannot hold a call or send keypad tones (LiveKit) does not get buttons that can only fail.
    @MainActor private var offersHoldAndKeypad: Bool { store.coordinator.backend.supportsHoldAndKeypad }
    private var transcriptScore: Double? {
        guard call.transcript?.state == .monitoring else { return nil }
        return call.transcript?.probability
    }
    private var voiceScore: Double? {
        guard let voice = call.deepfake, [.human, .ai, .uncertain].contains(voice.state) else { return nil }
        return voice.aiScore
    }
    private var needsSafetySteps: Bool { (transcriptScore ?? 0) >= 0.75 || (voiceScore ?? 0) >= 0.75 }
    private var veryHighSignal: Bool { (transcriptScore ?? 0) >= 0.9 || (voiceScore ?? 0) >= 0.9 }

    var body: some View {
        GeometryReader { geometry in
            ViewThatFits(in: .vertical) {
                callContent(height: geometry.size.height)
                ScrollView { callContent(height: 0) }.scrollIndicators(.hidden)
            }
        }
        .multilineTextAlignment(.center).foregroundStyle(Palette.ink)
        .background(RadialGradient(colors: [Palette.softAccent, Palette.surface, Palette.canvas], center: .topLeading, startRadius: 0, endRadius: 700).ignoresSafeArea())
        .onReceive(clock) { now = $0 }
        .sheet(isPresented: $showingGuardian) {
            GuardianAlertSheet(call: call, store: store)
        }
        .onChange(of: scenePhase) { phase in
            // iOS does not allow an app to intercept or cancel the Home gesture.
            // Remember an actual departure and offer one reminder on return.
            if phase == .background, veryHighSignal, !departureWarningShown {
                leftDuringHighRisk = true
            } else if phase == .active, leftDuringHighRisk, !departureWarningShown {
                leftDuringHighRisk = false
                departureWarningShown = true
                showingDepartureWarning = true
            }
        }
        .alert("Pause Before Sharing", isPresented: $showingDepartureWarning) {
            Button("End Call", role: .destructive) { perform { try await store.coordinator.end() } }
            Button("Alert Guardian") { showingGuardian = true }
            Button("Continue Call", role: .cancel) { }
        } message: {
            Text("This call had a very high experimental warning score. Don’t share codes, passwords, or move money. You can end the call and verify the caller independently.")
        }
    }
    private func callContent(height: CGFloat) -> some View {
        VStack(spacing: 12) {
            BrandWordmark(onDark: true).font(.subheadline).foregroundStyle(Palette.secondary)
            Avatar(person: call.person, size: 64).padding(.top, 4)
            Text(call.person.name).font(.title.weight(.medium)).accessibilityIdentifier("callCallerName")
            Text(call.person.number).font(.subheadline).foregroundStyle(Palette.secondary)
            Text(status).monospacedDigit().foregroundStyle(Palette.secondary)
            if call.connectedAt != nil {
                VStack(spacing: 10) {
                    Text("Caller’s voice").font(.caption.weight(.semibold))
                    HStack(spacing: 4) {
                        VoiceBadge(voice: call.voice, size: 13, onCall: true)
                        ResultHelpButton(title: "Voice labels", message: "A voice label estimates whether audio sounds human or AI-generated. It does not verify identity or prove a call is safe. Analyzing means the check is still running; Unknown means there is not enough information.", onDark: true)
                    }
                    Text(assessment).font(.caption).foregroundStyle(Palette.secondary)
                    if let voiceScore {
                        Text("Experimental voice warning score: \(Int((voiceScore * 100).rounded())) out of 100")
                            .font(.caption).foregroundStyle(Palette.secondary)
                    }
                    if let previous = call.lastDeepfakeResult,
                       let current = call.deepfake, [.waiting, .analyzing, .unavailable].contains(current.state) {
                        Text("Last result: \(previous.voice.label)").font(.caption.weight(.semibold))
                    }
                    Text("A human voice does not confirm who is calling.").font(.caption).foregroundStyle(Palette.secondary)
                }.padding(16).frame(maxWidth: .infinity)
                    .background(Palette.surface, in: RoundedRectangle(cornerRadius: 18))
            }
            if call.connectedAt != nil {
                let text = call.transcript ?? TranscriptAssessment(state: .listening, updatedAt: now)
                VStack(spacing: 8) {
                    Label("Scam warning", systemImage: "text.bubble").font(.caption.weight(.semibold))
                    Text(text.title).font(.subheadline.weight(.semibold))
                        .foregroundStyle(text.isWarning ? Palette.warning : Palette.ink)
                        .accessibilityIdentifier("transcriptAssessmentTitle")
                    Text(text.message).font(.caption).foregroundStyle(Palette.secondary)
                        .accessibilityIdentifier("transcriptAssessmentScore")
                    Text("Based on the caller’s words. A low score does not prove a call is safe.")
                        .font(.caption2).foregroundStyle(Palette.secondary)
                }.padding(16).frame(maxWidth: .infinity)
                    .background(Palette.surface, in: RoundedRectangle(cornerRadius: 18))
            }
            if call.connectedAt != nil && needsSafetySteps { safetySteps }
            Spacer(minLength: 8)
            if call.stage == .incoming {
                HStack {
                    action("Decline", "phone.down.fill", color: Palette.destructive) { try await store.coordinator.end() }
                    Spacer()
                    action("Accept", "phone.fill", color: Palette.action) { try await store.coordinator.answer() }
                }.padding(.horizontal, 12)
            } else {
                if showingKeypad {
                    PhoneKeypad { digit in perform { try await store.coordinator.sendDTMF(digit) } }
                } else {
                    HStack(spacing: 24) {
                        action(call.muted ? "unmute" : "mute", call.muted ? "mic.slash" : "mic", selected: call.muted) {
                            try await store.coordinator.setMuted(!call.muted)
                        }
                        action("speaker", "speaker.wave.2", selected: call.speaker) {
                            try store.coordinator.setSpeaker(!call.speaker)
                        }
                        if offersHoldAndKeypad {
                            action(call.stage == .held ? "resume" : "hold", "pause", selected: call.stage == .held) {
                                try await store.coordinator.setHeld(call.stage != .held)
                            }
                        }
                    }.disabled(call.connectedAt == nil)
                }
                if offersHoldAndKeypad {
                    Button(showingKeypad ? "Hide keypad" : "Keypad") { showingKeypad.toggle() }
                        .disabled(call.connectedAt == nil).padding(8)
                }
                action("End call", "phone.down.fill", color: Palette.destructive) { try await store.coordinator.end() }
            }
        }
        .padding(20).frame(maxWidth: 500).frame(minHeight: height).frame(maxWidth: .infinity)
    }
    private var safetySteps: some View {
        VStack(spacing: 10) {
            Label("Pause Before Sharing", systemImage: "hand.raised.fill").font(.subheadline.weight(.semibold))
                .foregroundStyle(Palette.warning)
            Text("Don’t share codes, passwords, or move money. Hang up and verify using a number you already know.")
                .font(.caption).fixedSize(horizontal: false, vertical: true)
            Button { showingGuardian = true } label: {
                Label("Alert Guardian", systemImage: "person.2.fill").frame(maxWidth: .infinity, minHeight: 44)
            }.buttonStyle(.bordered).tint(Palette.accent).accessibilityIdentifier("alertGuardianButton")
            Text("Warning scores are experimental. They do not confirm fraud or identity.")
                .font(.caption2).foregroundStyle(Palette.secondary)
        }.padding(16).frame(maxWidth: .infinity)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: 18))
    }
    private var status: String {
        switch call.stage {
        case .incoming: return "Incoming call"
        case .connecting: return "Connecting…"
        case .held: return "On hold"
        case .connected: return callDuration(call.connectedAt.map { max(0, Int(now.timeIntervalSince($0))) } ?? 0)
        }
    }
    private var assessment: String {
        if call.deepfake != nil { return voiceAssessment.message }
        switch call.voice {
        case .analyzing: return "Checking the caller’s voice…"
        case .ai: return "This voice may be AI-generated."
        case .human: return "This voice appears to be human."
        case .unknown: return "A voice assessment is not available."
        }
    }
    private func action(_ title: String, _ symbol: String, color: Color = Palette.softAccent, selected: Bool = false,
                        operation: @escaping () async throws -> Void) -> some View {
        Button { perform(operation) } label: {
            VStack(spacing: 9) {
                Image(systemName: symbol).scaledFont(size: 27)
                    .foregroundStyle(title == "Decline" || title == "End call" ? Color.white : selected || title == "Accept" ? Palette.actionInk : Palette.ink)
                    .frame(width: 64, height: 64).background(selected ? Palette.action : color, in: Circle())
                Text(title).font(.caption)
            }
        }.buttonStyle(CallActionStyle()).disabled(busy).accessibilityValue(selected ? "On" : "Off")
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
