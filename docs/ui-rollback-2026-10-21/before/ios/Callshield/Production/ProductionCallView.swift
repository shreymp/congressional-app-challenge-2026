import SwiftUI

private enum CallDetail: Hashable { case voice, words, safety, controls }
private struct CallDetailAnchors: PreferenceKey {
    static var defaultValue: [CallDetail: Anchor<CGRect>] = [:]
    static func reduce(value: inout [CallDetail: Anchor<CGRect>], nextValue: () -> [CallDetail: Anchor<CGRect>]) {
        value.merge(nextValue(), uniquingKeysWith: { _, new in new })
    }
}

struct ProductionCallView: View {
    let call: PhoneCall
    @EnvironmentObject private var store: ProductionStore
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var textSize
    @State private var showingKeypad = false
    @State private var showingGuardian = false
    @State private var busy = false
    @State private var leftDuringHighRisk = false
    @State private var departureWarningShown = false
    @State private var showingDepartureWarning = false
    @State private var selectedDetail: CallDetail?
    private let clock = Timer.publish(every: 1, on: .main, in: .common).autoconnect()
    @State private var now = Date()

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
        VStack(spacing: 14) {
            Spacer(minLength: 0)
            callerHeader
            if call.connectedAt != nil && !showingKeypad {
                HStack(spacing: 12) {
                    summaryButton(.voice, title: "Voice", value: shortVoice, symbol: "waveform")
                    summaryButton(.words, title: "Words", value: shortTranscript, symbol: "text.bubble")
                }
                if needsSafetySteps { compactSafetySteps }
            }
            Spacer(minLength: 8)
            callControls
                .anchorPreference(key: CallDetailAnchors.self, value: .bounds) { [.controls: $0] }
        }
        .frame(maxWidth: 500).frame(maxWidth: .infinity)
        .padding(.horizontal, 24).padding(.top, 12).padding(.bottom, 16)
        .overlayPreferenceValue(CallDetailAnchors.self) { anchors in
            GeometryReader { geometry in
                if let detail = selectedDetail, let anchor = anchors[detail] {
                    let controlTop = anchors[.controls].map { geometry[$0].minY } ?? geometry.size.height - 230
                    let bottom = max(120, controlTop - 12)
                    let top = max(8, min(geometry[anchor].maxY + 8, bottom - 160))
                    let height = min(260, bottom - top)
                    Color.black.opacity(0.001).contentShape(Rectangle())
                        .frame(height: max(0, controlTop)).frame(maxHeight: .infinity, alignment: .top)
                        .onTapGesture { selectedDetail = nil }.accessibilityHidden(true)
                    detailPopover(detail)
                        .frame(width: min(440, geometry.size.width - 32), height: height)
                        .position(x: geometry.size.width / 2, y: top + height / 2)
                }
            }
        }
        .foregroundStyle(Palette.ink)
        .background {
            LinearGradient(colors: [Color(hex: 0x2B3545), Color(hex: 0x111721)], startPoint: .topLeading, endPoint: .bottomTrailing)
                .ignoresSafeArea()
        }
        .preferredColorScheme(.dark)
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

    private var callerHeader: some View {
        VStack(spacing: 8) {
            if !textSize.isAccessibilitySize && !showingKeypad { Avatar(person: call.person, size: 76) }
            Text(call.person.name).font(textSize.isAccessibilitySize || showingKeypad ? .headline : .largeTitle.weight(.semibold))
                .multilineTextAlignment(.center).lineLimit(textSize.isAccessibilitySize ? 1 : 2)
                .accessibilityLabel("\(call.person.name), \(call.person.number)")
                .accessibilityIdentifier("callCallerName")
            if !call.person.number.isEmpty && !textSize.isAccessibilitySize && !showingKeypad {
                Text(call.person.number).font(.body).foregroundStyle(Palette.secondary)
            }
            Text(status).font(.caption).monospacedDigit().foregroundStyle(Palette.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private var shortVoice: String {
        switch call.voice { case .human: return "Human"; case .ai: return "AI-like"; case .analyzing: return "Checking"; case .unknown: return "Unclear" }
    }
    private var shortTranscript: String {
        guard let score = transcriptScore else { return call.transcript?.state == .listening ? "Listening" : "No score" }
        return "\(Int((score * 100).rounded()))/100"
    }
    private func summaryButton(_ detail: CallDetail, title: String, value: String, symbol: String) -> some View {
        Button { selectedDetail = selectedDetail == detail ? nil : detail } label: {
            VStack(spacing: 4) {
                HStack(spacing: 4) {
                    if textSize.isAccessibilitySize { Text(title) }
                    else { Label(title, systemImage: symbol) }
                    Image(systemName: "chevron.down")
                }.font(.caption2).foregroundStyle(Palette.secondary)
                Text(value).font(.subheadline.weight(.semibold)).monospacedDigit().minimumScaleFactor(0.7)
                    .foregroundStyle(detail == .words && (transcriptScore ?? 0) >= 0.75 ? Palette.warning : Palette.ink)
            }.lineLimit(1).frame(maxWidth: .infinity, minHeight: 52).padding(.vertical, 8)
                .background(.white.opacity(0.07), in: RoundedRectangle(cornerRadius: 18))
                .overlay(RoundedRectangle(cornerRadius: 18).stroke(.white.opacity(0.12)))
                .contentShape(Rectangle())
        }.buttonStyle(.plain)
        .accessibilityLabel(detail == .voice ? "Caller’s voice: \(call.voice.label). Show details" : "Caller’s words: \(call.transcript?.title ?? "Listening"). Experimental score \(shortTranscript). Show details")
        .accessibilityIdentifier(detail == .voice ? "voiceDetailsButton" : "transcriptDetailsButton")
        .anchorPreference(key: CallDetailAnchors.self, value: .bounds) { [detail: $0] }
    }
    private var compactSafetySteps: some View {
        VStack(spacing: 6) {
            Button { selectedDetail = .safety } label: {
                Label("Don’t share codes or money", systemImage: "hand.raised.fill")
                    .font(.caption).multilineTextAlignment(.center).lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true).frame(minHeight: 44)
            }.buttonStyle(.plain).foregroundStyle(Palette.warning)
                .accessibilityLabel("Pause before sharing. Don’t share codes, passwords, or move money. Show safety steps")
                .accessibilityIdentifier("safetyDetailsButton")
                .anchorPreference(key: CallDetailAnchors.self, value: .bounds) { [.safety: $0] }
            Button { showingGuardian = true } label: {
                Label("Alert Guardian", systemImage: "person.2.fill").font(.caption).lineLimit(1).minimumScaleFactor(0.7)
                    .frame(maxWidth: .infinity, minHeight: 44)
            }.buttonStyle(.bordered).tint(Palette.accent).accessibilityIdentifier("alertGuardianButton")
        }
    }

    private func detailPopover(_ detail: CallDetail) -> some View {
        VStack(spacing: 0) {
            HStack {
                Text(detail == .voice ? "Voice Details" : detail == .words ? "Word Details" : "Safety Steps")
                    .font(.headline).lineLimit(1).minimumScaleFactor(0.65)
                Spacer(minLength: 8)
                Button { selectedDetail = nil } label: { Image(systemName: "xmark").frame(width: 44, height: 44).contentShape(Rectangle()) }
                    .accessibilityLabel("Close details").accessibilityIdentifier("closeCallDetails")
            }.padding(.horizontal, 18)
            Divider()
            ScrollView {
                switch detail {
                case .voice: voicePanel
                case .words: transcriptPanel
                case .safety: safetySteps
                case .controls: EmptyView()
                }
            }
        }
        .background(Palette.surface, in: RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(Palette.line, lineWidth: 1))
        .shadow(color: .black.opacity(0.18), radius: 18, y: 6)
        .accessibilityElement(children: .contain).accessibilityIdentifier("callDetailPopover")
    }

    private var safetySteps: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Pause Before Sharing", systemImage: "hand.raised.fill")
                .font(.headline).foregroundStyle(Palette.warning)
            Text("Don’t share security codes, passwords, or move money during this call.")
                .font(.body).fixedSize(horizontal: false, vertical: true)
            Text("Hang up and contact the organization using a number you already know.")
                .font(.subheadline).foregroundStyle(Palette.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Button { showingGuardian = true } label: {
                Label("Alert Guardian", systemImage: "person.crop.circle.badge.exclamationmark")
                    .frame(maxWidth: .infinity, minHeight: 44)
            }
            .buttonStyle(.borderedProminent).tint(Palette.accent)
            .foregroundStyle(Palette.onAccent)
            .accessibilityIdentifier("alertGuardianButton")
            Text("Warning scores can be wrong. They do not confirm fraud or identity.")
                .font(.caption).foregroundStyle(Palette.secondary)
        }
        .padding(18).frame(maxWidth: .infinity, alignment: .leading)
        .background(Palette.warningSurface, in: RoundedRectangle(cornerRadius: 20))
    }

    private var voicePanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Caller’s voice", systemImage: "waveform").font(.caption).foregroundStyle(Palette.secondary)
            VoiceBadge(voice: call.voice, size: 15)
            Text(assessment).font(.body).fixedSize(horizontal: false, vertical: true)
            if let previous = call.lastDeepfakeResult,
               let current = call.deepfake, [.waiting, .analyzing, .unavailable].contains(current.state) {
                Text("Last result: \(previous.voice.label)").font(.subheadline).foregroundStyle(Palette.secondary)
            }
            Text("Voice estimates can be wrong. They do not verify who is calling.")
                .font(.caption).foregroundStyle(Palette.secondary).fixedSize(horizontal: false, vertical: true)
        }
        .padding(18).frame(maxWidth: .infinity, alignment: .leading)
        .background(Palette.surface, in: RoundedRectangle(cornerRadius: 20))
    }

    private var transcriptPanel: some View {
        let text = call.transcript ?? TranscriptAssessment(state: .listening, updatedAt: now)
        return VStack(alignment: .leading, spacing: 12) {
            Text(text.title).font(.headline)
                .foregroundStyle(text.isWarning ? Palette.warning : Palette.ink)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("transcriptAssessmentTitle")
            Text(text.message).font(.body).foregroundStyle(Palette.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("transcriptAssessmentScore")
            Text("Verify the caller independently before sharing codes or money.")
                .font(.caption).foregroundStyle(Palette.secondary).fixedSize(horizontal: false, vertical: true)
        }
        .padding(18).frame(maxWidth: .infinity, alignment: .leading)
        .background(Palette.surface, in: RoundedRectangle(cornerRadius: 20))
    }

    @ViewBuilder private var callControls: some View {
        VStack(spacing: 14) {
            if call.stage == .incoming {
                HStack(spacing: 40) {
                    action("Decline", "phone.down.fill", color: Palette.coral) { try await store.coordinator.end() }
                    action("Accept", "phone.fill", color: Palette.teal) { try await store.coordinator.answer() }
                }.frame(maxWidth: .infinity)
            } else {
                if showingKeypad {
                    PhoneKeypad { digit in perform { try await store.coordinator.sendDTMF(digit) } }
                        .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                } else {
                    HStack(alignment: .top, spacing: 12) {
                        action(call.muted ? "Unmute" : "Mute", call.muted ? "mic.slash.fill" : "mic.fill", selected: call.muted, toggle: true) {
                            try await store.coordinator.setMuted(!call.muted)
                        }
                        Button { selectedDetail = nil; showingKeypad = true } label: {
                            VStack(spacing: 8) {
                                Image(systemName: "circle.grid.3x3.fill").font(.title2)
                                    .frame(width: 64, height: 64).background(.white.opacity(0.12), in: Circle())
                                Text("Keypad").font(.caption).lineLimit(1).minimumScaleFactor(0.65)
                            }.frame(minWidth: 72, maxWidth: .infinity)
                        }.buttonStyle(CallActionStyle()).disabled(!offersHoldAndKeypad)
                            .opacity(offersHoldAndKeypad ? 1 : 0.4)
                            .accessibilityHint(offersHoldAndKeypad ? "" : "Unavailable for this call")
                        action("Speaker", "speaker.wave.2.fill", selected: call.speaker, toggle: true) { try store.coordinator.setSpeaker(!call.speaker) }
                    }.disabled(call.connectedAt == nil)
                }
                if showingKeypad {
                    Button("Hide Keypad") { showingKeypad = false }
                        .font(.subheadline).frame(minHeight: 44)
                }
                Button { perform { try await store.coordinator.end() } } label: {
                    VStack(spacing: 8) {
                        Image(systemName: "phone.down.fill").font(.title)
                            .foregroundStyle(.white).frame(width: 80, height: 80)
                            .background(Palette.coral, in: Circle())
                        Text("End Call").font(.caption).foregroundStyle(.white)
                    }
                }
                .buttonStyle(CallActionStyle()).disabled(busy)
                .accessibilityLabel("End call")
            }
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
    private var assessment: String {
        if let deepfake = call.deepfake { return deepfake.message }
        switch call.voice {
        case .analyzing: return "Checking the caller’s voice…"
        case .ai: return "This voice may be AI-generated."
        case .human: return "This voice appears to be human."
        case .unknown: return "A voice assessment is not available."
        }
    }
    private func action(_ title: String, _ symbol: String, color: Color? = nil, selected: Bool = false, toggle: Bool = false,
                        operation: @escaping () async throws -> Void) -> some View {
        Button { perform(operation) } label: {
            VStack(spacing: 8) {
                Image(systemName: symbol).font(.title2)
                    .foregroundStyle(color != nil ? Color.white : selected ? Color(hex: 0x17243A) : .white)
                    .frame(width: 64, height: 64)
                    .background(color ?? (selected ? Color.white : .white.opacity(0.12)), in: Circle())
                Text(title).font(.caption).multilineTextAlignment(.center).lineLimit(1).minimumScaleFactor(0.65)
            }.frame(minWidth: 72, maxWidth: .infinity)
        }
        .buttonStyle(CallActionStyle()).disabled(busy)
        .accessibilityValue(toggle ? (selected ? "On" : "Off") : "")
    }
    private func perform(_ operation: @escaping () async throws -> Void) {
        guard !busy else { return }
        selectedDetail = nil
        busy = true
        Task {
            defer { busy = false }
            do { try await operation() }
            catch { store.errorMessage = error.localizedDescription }
        }
    }
}
