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
    private var voiceAssessment: DeepfakeAssessment {
        let value = call.deepfake ?? DeepfakeAssessment(state: .analyzing, updatedAt: now)
        guard let connectedAt = call.connectedAt,
              now.timeIntervalSince(connectedAt) >= DeepfakeAssessment.initialDeadline else { return value }
        return value.finalized(at: now)
    }
    private var needsSafetySteps: Bool { (transcriptScore ?? 0) >= 0.75 || (voiceScore ?? 0) >= 0.75 }
    private var veryHighSignal: Bool { (transcriptScore ?? 0) >= 0.9 || (voiceScore ?? 0) >= 0.9 }

    var body: some View {
        GeometryReader { geometry in
            // The call screen never scrolls: it drops the logo and avatar, then caps text size, until it fits.
            ViewThatFits(in: .vertical) {
                callContent(height: geometry.size.height, compact: false)
                callContent(height: geometry.size.height, compact: true)
                callContent(height: geometry.size.height, compact: true).dynamicTypeSize(...DynamicTypeSize.accessibility2)
                callContent(height: geometry.size.height, compact: true).dynamicTypeSize(...DynamicTypeSize.accessibility1)
                callContent(height: geometry.size.height, compact: true).dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                callContent(height: geometry.size.height, compact: true).dynamicTypeSize(...DynamicTypeSize.large)
            }
        }
        .multilineTextAlignment(.center).foregroundStyle(Palette.ink)
        // Blue-gray from the top-left corner, strong enough to read on a real screen, fading to the page color.
        .background(RadialGradient(stops: [.init(color: Palette.callGlow, location: 0),
                                            .init(color: Palette.lavender, location: 0.35),
                                            .init(color: Palette.canvas, location: 1)],
                                    center: .topLeading, startRadius: 0, endRadius: 950).ignoresSafeArea())
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
    private func callContent(height: CGFloat, compact: Bool) -> some View {
        VStack(spacing: compact ? 8 : 12) {
            if !compact {
                BrandWordmark(onDark: true).font(.subheadline).foregroundStyle(Palette.secondary)
                Avatar(person: call.person, size: 64).padding(.top, 4)
            }
            Text(call.person.name).font(.title.weight(.medium)).accessibilityIdentifier("callCallerName")
            Text("\(call.person.number) · \(status)").font(.subheadline).monospacedDigit().foregroundStyle(Palette.secondary)
            if call.connectedAt != nil { verdictCard }
            Spacer(minLength: compact ? 4 : 8)
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
        .padding(compact ? 16 : 20).frame(maxWidth: 500).frame(minHeight: height).frame(maxWidth: .infinity)
    }
    /// One card for both checks: the header takes the most serious finished result, each row keeps its own.
    private var verdictCard: some View {
        let verdict = self.verdict
        return VStack(spacing: 0) {
            HStack(spacing: 14) {
                Group {
                    if verdict.level == nil && verdict.checking {
                        CheckingSpinner(size: 32)
                    } else {
                        // Fixed size: the icon stays inside its frame at the largest text sizes.
                        Image(systemName: verdict.level?.symbol ?? "minus.circle").font(.system(size: 32, weight: .semibold))
                    }
                }.frame(width: 40, height: 40).accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(verdict.headline).scaledFont(size: 26, weight: .heavy)
                    Text(verdict.advice).scaledFont(size: 15, weight: .medium).fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
            .padding(18)
            .foregroundStyle(verdict.level?.ink ?? Palette.accent)
            .background(verdict.level?.fill ?? Palette.softAccent)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("callVerdictHeadline")
            VStack(alignment: .leading, spacing: 14) {
                checkRow(voiceCheck)
                checkRow(wordsCheck)
                if verdict.level == .high || needsSafetySteps {
                    Button { showingGuardian = true } label: {
                        Text("Alert Guardian").font(.headline)
                            .frame(maxWidth: .infinity, minHeight: 48)
                            .foregroundStyle(Palette.actionInk)
                            .background(Palette.action, in: RoundedRectangle(cornerRadius: 12))
                    }.buttonStyle(.plain).accessibilityIdentifier("alertGuardianButton")
                }
            }.padding(EdgeInsets(top: 14, leading: 18, bottom: 16, trailing: 18))
        }
        .multilineTextAlignment(.leading)
        .background(Palette.surface)
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .shadow(color: Palette.line, radius: 0, x: 0, y: 1)
        .padding(.top, 6)
    }
    private func checkRow(_ check: CheckResult) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(check.name).font(.subheadline).foregroundStyle(Palette.secondary).frame(minWidth: 56, alignment: .leading)
                Text(check.label).font(.headline).accessibilityIdentifier(check.titleID)
                Spacer(minLength: 4)
                Text(check.score.map { "\($0)%" } ?? "—").monospacedDigit()
                    .scaledFont(size: 23, weight: .bold).fixedSize()
                    .accessibilityLabel(check.score.map { "\($0)%" } ?? "No score")
                    .accessibilityIdentifier(check.scoreID)
            }
            ScoreBar(fraction: Double(check.score ?? 0) / 100, color: check.level?.bar ?? Palette.line, checking: check.checking)
            if let note = check.note {
                Text(note).font(.caption.weight(.semibold)).foregroundStyle(Palette.secondary)
            }
        }
    }
    private var voiceCheck: CheckResult {
        let voice = voiceAssessment
        let score = voice.score.map { Int($0.rounded()) }
        var check = CheckResult(name: "Voice", label: "Checking…", level: nil, score: nil, checking: true,
                                titleID: "deepfakeAssessmentTitle", scoreID: "deepfakeAssessmentScore")
        switch voice.state {
        case .waiting, .analyzing:
            if let previous = call.lastDeepfakeResult { check.note = "Last result: \(previous.voice.label)" }
        case .human: (check.label, check.level, check.score, check.checking) = ("Sounds human", .low, score, false)
        case .ai: (check.label, check.level, check.score, check.checking) = ("Likely AI", .high, score, false)
        case .uncertain: (check.label, check.level, check.score, check.checking) = ("Not sure yet", .caution, score, false)
        case .unavailable: (check.label, check.checking) = ("Unavailable", false)
        }
        return check
    }
    private var wordsCheck: CheckResult {
        let text = call.transcript ?? TranscriptAssessment(state: .listening, updatedAt: now)
        var check = CheckResult(name: "Words", label: "Listening…", level: nil, score: text.score, checking: false,
                                titleID: "transcriptAssessmentTitle", scoreID: "transcriptAssessmentScore")
        switch text.risk {
        case .high: (check.label, check.level) = ("Scam language", .high)
        case .medium: (check.label, check.level) = ("Some warning signs", .caution)
        case .low: (check.label, check.level) = ("No scam language", .low)
        case nil:
            check.score = nil
            switch text.state {
            case .listening: check.checking = true
            case .stale: (check.label, check.checking) = ("Updating…", true)
            case .insufficientEvidence: check.label = "Not enough to judge"
            case .disabled: check.label = "Off"
            default: check.label = "Unavailable"
            }
        }
        return check
    }
    private var verdict: (level: RiskLevel?, headline: String, advice: String, checking: Bool) {
        let voice = voiceCheck, words = wordsCheck
        let checking = voice.checking || words.checking
        let worst = [voice.level, words.level].compactMap { $0 }.max()
        let voiceHigh = voice.level == .high, wordsHigh = words.level == .high
        switch worst {
        case nil where checking:
            return (nil, "Checking this call", "Results appear as the caller speaks.", true)
        case nil:
            return (nil, "Checks unavailable", "Your call can continue. Verify who is calling before sharing anything.", false)
        case .high where voiceHigh && wordsHigh:
            return (.high, "Likely scam", "Don’t share money, codes, or passwords.", checking)
        case .high where wordsHigh:
            let advice = voice.checking ? "Scam language heard. Still checking the voice."
                : voice.level == .low ? "The voice sounds human, but a real person can still be a scammer."
                : "Don’t share money, codes, or passwords."
            return (.high, "Likely scam", advice, checking)
        case .high:
            let advice = words.checking ? "The voice may be AI. Still listening to the words."
                : "The words sound normal, but the voice may be AI. Verify who is calling."
            return (.high, "Possible fake voice", advice, checking)
        case .caution:
            return (.caution, "Be careful", "Check who is calling before sharing anything.", checking)
        case .low:
            return (.low, "No strong signs", checking ? "So far. Still checking the other signal." : "Stay alert. This doesn’t prove who is calling.", checking)
        }
    }
    private var status: String {
        switch call.stage {
        case .incoming: return "Incoming call"
        case .connecting: return "Connecting…"
        case .held: return "On hold"
        case .connected: return callDuration(call.connectedAt.map { max(0, Int(now.timeIntervalSince($0))) } ?? 0)
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

/// The call-screen band for one check's finished result; ordered so the worst one wins the header.
private enum RiskLevel: Int, Comparable {
    case low, caution, high
    static func < (lhs: RiskLevel, rhs: RiskLevel) -> Bool { lhs.rawValue < rhs.rawValue }
    var symbol: String {
        switch self {
        case .high: return "exclamationmark.triangle"
        case .caution: return "exclamationmark.circle"
        case .low: return "checkmark"
        }
    }
    var fill: Color {
        switch self {
        case .high: return Palette.danger
        case .caution: return Palette.caution
        case .low: return Palette.calm
        }
    }
    var ink: Color { self == .caution ? Palette.verdictInk : .white }
    var bar: Color { self == .caution ? Palette.cautionStrong : fill }
}

private struct CheckResult {
    let name: String
    var label: String
    var level: RiskLevel?
    var score: Int?
    var checking: Bool
    let titleID: String
    let scoreID: String
    var note: String? = nil
}

/// A score bar; while its check is running a short segment sweeps across instead.
private struct ScoreBar: View {
    let fraction: Double
    let color: Color
    let checking: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                Capsule().fill(Palette.softAccent)
                if checking {
                    TimelineView(.animation) { context in
                        let time = context.date.timeIntervalSinceReferenceDate
                        let segment = geometry.size.width * 0.28
                        let phase = (sin(time * 2.6) + 1) / 2
                        Capsule().fill(Palette.line).frame(width: segment)
                            .offset(x: reduceMotion ? 0 : phase * (geometry.size.width - segment))
                            .opacity(reduceMotion ? 0.45 + 0.55 * phase : 1)
                    }
                } else {
                    Capsule().fill(color).frame(width: geometry.size.width * min(max(fraction, 0), 1))
                }
            }
        }
        .frame(height: 8)
        .animation(reduceMotion ? nil : .easeOut(duration: 0.5), value: fraction)
        .accessibilityHidden(true)
    }
}

/// Spins while both checks are still running; pulses instead when Reduce Motion is on.
private struct CheckingSpinner: View {
    let size: CGFloat
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        TimelineView(.animation) { context in
            let time = context.date.timeIntervalSinceReferenceDate
            Circle().trim(from: 0, to: 0.72)
                .stroke(style: StrokeStyle(lineWidth: size * 0.11, lineCap: .round))
                .rotationEffect(.degrees(reduceMotion ? 0 : time.truncatingRemainder(dividingBy: 1) * 360))
                .opacity(reduceMotion ? 0.5 + 0.5 * abs(sin(time * 2)) : 1)
                .frame(width: size, height: size)
        }
    }
}
