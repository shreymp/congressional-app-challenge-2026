import Foundation

/// Independent of CallKit so service-event ordering can be verified without making calls.
struct PhoneSessionState {
    private(set) var current: PhoneCall?

    mutating func begin(_ call: PhoneCall) -> Bool {
        guard current == nil else { return false }
        current = call
        return true
    }
    mutating func connected(id: UUID, at date: Date) {
        guard current?.id == id, current?.connectedAt == nil else { return }
        current?.connectedAt = date
        current?.stage = .connected
    }
    mutating func connecting(id: UUID) {
        guard current?.id == id, current?.stage == .incoming else { return }
        current?.stage = .connecting
    }
    mutating func assess(id: UUID, voice: Voice) {
        guard current?.id == id, current?.connectedAt != nil else { return }
        current?.voice = voice
    }
    mutating func assessDeepfake(id: UUID, assessment: DeepfakeAssessment) {
        guard current?.id == id, current?.connectedAt != nil else { return }
        current?.deepfake = assessment
        current?.voice = assessment.voice
        if [.ai, .human, .uncertain].contains(assessment.state) {
            current?.lastDeepfakeResult = assessment
        }
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
                               transcript: call.connectedAt == nil ? nil : (call.lastTranscriptResult ?? call.transcript))
    }
}

