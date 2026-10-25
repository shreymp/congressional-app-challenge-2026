import Foundation

/// Independent of CallKit so service-event ordering can be verified without making calls.
struct PhoneSessionState {
    private(set) var current: PhoneCall?

    mutating func begin(_ call: PhoneCall) -> Bool {
        guard current == nil else { return false }
        current = call
        return true
    }
    mutating func connected(id: UUID, at date: Date, monotonicTime: TimeInterval = ProcessInfo.processInfo.systemUptime) {
        guard current?.id == id, current?.connectedAt == nil else { return }
        current?.connectedAt = date
        current?.connectedMonotonicTime = monotonicTime
        recordTiming("connected", monotonicTime: monotonicTime)
        current?.stage = .connected
        current?.voice = .analyzing
        current?.deepfake = DeepfakeAssessment(state: .analyzing, updatedAt: date)
    }
    mutating func connecting(id: UUID) {
        guard current?.id == id, current?.stage == .incoming else { return }
        current?.stage = .connecting
    }
    mutating func assess(id: UUID, voice: Voice) {
        let state: DeepfakeAssessment.State
        switch voice {
        case .human: state = .human
        case .ai: state = .ai
        case .unknown: state = .uncertain
        case .analyzing: state = .analyzing
        }
        assessDeepfake(id: id, assessment: DeepfakeAssessment(state: state, updatedAt: Date()))
    }
    mutating func assessDeepfake(id: UUID, assessment: DeepfakeAssessment,
                                monotonicTime: TimeInterval = ProcessInfo.processInfo.systemUptime) {
        guard current?.id == id, let connectedAt = current?.connectedAt else { return }
        // Legacy warm-up heartbeats do not erase completed evidence; explicit quality/freshness does.
        if [.waiting, .analyzing].contains(assessment.state), assessment.freshness == nil,
           let previous = current?.deepfake, [.human, .ai, .uncertain].contains(previous.state),
           previous.windows >= 2 { return }
        let assessment = assessment.updatedAt.timeIntervalSince(connectedAt) >= DeepfakeAssessment.initialDeadline
            ? assessment.finalized(at: assessment.updatedAt) : assessment
        if !((current?.analysisTiming.contains { $0.event == "first_packet_received" }) ?? false), assessment.sequence != nil {
            recordTiming("first_packet_received", monotonicTime: monotonicTime, assessment: assessment)
        }
        current?.deepfake = assessment
        current?.voice = assessment.voice
        if [.ai, .human, .uncertain].contains(assessment.state), !assessment.isStale {
            current?.lastDeepfakeResult = assessment
        }
    }
    mutating func finalizeInitialAssessment(id: UUID, at date: Date,
                                           monotonicTime: TimeInterval = ProcessInfo.processInfo.systemUptime) {
        guard current?.id == id, let connectedAt = current?.connectedAt,
              date.timeIntervalSince(connectedAt) >= DeepfakeAssessment.initialDeadline else { return }
        recordTiming("initial_deadline", monotonicTime: monotonicTime)
        let latest = current?.deepfake ?? DeepfakeAssessment(state: .analyzing, updatedAt: date)
        assessDeepfake(id: id, assessment: latest.finalized(at: date))
    }
    mutating func recordVoiceDisplay(id: UUID, monotonicTime: TimeInterval = ProcessInfo.processInfo.systemUptime) {
        guard current?.id == id, let assessment = current?.deepfake else { return }
        let previous = current?.analysisTiming.last { $0.event == "displayed" }
        guard previous?.displayedTitle != assessment.title || previous?.sequence != assessment.sequence else { return }
        recordTiming("displayed", monotonicTime: monotonicTime, assessment: assessment)
    }
    private mutating func recordTiming(_ event: String, monotonicTime: TimeInterval, assessment: DeepfakeAssessment? = nil) {
        guard let origin = current?.connectedMonotonicTime else { return }
        let sample = CallAnalysisTiming(event: event, elapsedSeconds: max(0, monotonicTime - origin),
            streamID: assessment?.streamID, sequence: assessment?.sequence,
            windowCount: assessment?.windows, windowID: assessment?.windowID, displayedTitle: event == "displayed" ? assessment?.title : nil)
        current?.analysisTiming.append(sample)
        if (current?.analysisTiming.count ?? 0) > 256 { current?.analysisTiming.remove(at: 1) }
    }
    mutating func assessTranscript(id: UUID, assessment: TranscriptAssessment) {
        guard current?.id == id, current?.connectedAt != nil else { return }
        current?.transcript = assessment
        if assessment.state == .monitoring { current?.lastTranscriptResult = assessment }
    }
    mutating func setMuted(_ muted: Bool, id: UUID) {
        guard current?.id == id else { return }
        current?.muted = muted
    }
    mutating func setSpeaker(_ speaker: Bool, id: UUID) {
        guard current?.id == id else { return }
        current?.speaker = speaker
    }
    mutating func setHeld(_ held: Bool, id: UUID) {
        guard current?.id == id, current?.connectedAt != nil else { return }
        current?.stage = held ? .held : .connected
    }
    mutating func finish(id: UUID, outcome: PhoneCallOutcome, at date: Date) -> PhoneCallRecord? {
        guard let call = current, call.id == id else { return nil }
        current = nil
        let assessment = call.lastDeepfakeResult ?? call.deepfake
        let voice = assessment?.voice ?? call.voice
        return PhoneCallRecord(id: call.id, person: call.person, date: call.createdAt,
                               duration: call.connectedAt.map { max(0, Int(date.timeIntervalSince($0))) } ?? 0,
                               direction: call.direction, outcome: outcome,
                               voice: call.connectedAt == nil || voice == .analyzing ? .unknown : voice,
                               deepfake: call.connectedAt == nil ? nil : assessment,
                               transcript: call.connectedAt == nil ? nil : (call.lastTranscriptResult ?? call.transcript),
                               analysisTiming: call.connectedAt == nil ? nil : call.analysisTiming)
    }
}

