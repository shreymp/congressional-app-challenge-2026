import Foundation

/// Persisted voice evidence. Scores are heuristic, never calibrated probabilities.
/// `updatedAt` is packet receipt; evidence age comes only from explicit model metadata.
struct DeepfakeAssessment: Codable, Equatable {
    enum State: String, Codable { case waiting, analyzing, human, ai, uncertain, unavailable }
    let state: State
    let updatedAt: Date
    var windows: Int = 0
    var score: Double? = nil
    var recentAI: Bool? = nil
    var currentScore: Double? = nil
    var evidenceStart: Double? = nil
    var evidenceEnd: Double? = nil
    var evidenceAge: Double? = nil
    var freshness: String? = nil
    var analysisStatus: String? = nil
    var qualityReason: String? = nil
    var statusReason: String? = nil
    var currentWarning: Bool? = nil
    var historicalWarnings: [WarningEvent]? = nil
    var pendingState: State? = nil
    var scoringMethod: String? = nil
    var streamID: UUID? = nil
    var sequence: Int? = nil
    var windowID: Int? = nil

    struct WarningEvent: Codable, Equatable {
        let id: String
        let start_sec: Double
        let end_sec: Double
        let current: Bool
    }
    static let initialDeadline: TimeInterval = 15
    static let evidenceFreshnessLimit: TimeInterval = 20

    /// A warning qualifies the headline without asserting a confident AI classification.
    var hasCurrentWarning: Bool {
        freshness != "stale" && freshness != "none" && analysisStatus != "unavailable"
            && (currentWarning == true || recentAI == true)
    }
    var isStale: Bool { freshness == "stale" || analysisStatus == "stale" }
    var hasQualityFailure: Bool { qualityReason != nil || freshness == "none" }
    var historyTitle: String { hasCurrentWarning ? "AI-like evidence during this call" : "Recorded result: " + title }
    var title: String {
        if hasCurrentWarning { return "AI-like voice detected recently" }
        if isStale { return "Waiting for fresh speech" }
        if hasQualityFailure {
            switch qualityReason {
            case "audio_too_quiet": return "Audio too quiet"
            case "audio_too_noisy": return "Audio too noisy"
            case "audio_distorted": return "Audio distorted"
            default: return state == .unavailable ? "Analysis unavailable" : "Not enough usable speech"
            }
        }
        switch state {
        case .waiting, .analyzing: return "Analyzing voice"
        case .human: return scoringMethod == "call-evidence-v1" ? "Whole-call summary: likely human" : "Likely human"
        case .ai: return "Likely AI"
        case .uncertain: return "Inconclusive"
        case .unavailable: return "Analysis unavailable"
        }
    }
    var voice: Voice {
        if hasCurrentWarning || isStale || hasQualityFailure { return .unknown }
        switch state {
        case .human: return .human
        case .ai: return .ai
        case .waiting, .analyzing: return .analyzing
        default: return .unknown
        }
    }
    var scoreText: String {
        guard let score else { return "Whole-call evidence unavailable" }
        return "Whole-call evidence: \(String(format: "%.1f", score))/100 · heuristic"
    }
    var currentScoreText: String? {
        guard let currentScore, scoringMethod == "call-evidence-v2" else { return nil }
        return "Recent voice evidence: \(String(format: "%.1f", currentScore))/100 · heuristic"
    }
    var pendingMessage: String? {
        guard let pendingState, pendingState != state else { return nil }
        let label: String
        switch pendingState {
        case .ai: label = "AI-like"
        case .human: label = "human-like"
        default: label = "inconclusive"
        }
        return "Recent evidence is moving toward \(label). Waiting for enough consistent usable speech before changing the assessment."
    }
    var historyMessage: String {
        if hasCurrentWarning { return "AI-like voice evidence was detected during this call. This was a qualified warning, not an identity check." }
        switch state {
        case .waiting: return "Not enough caller speech for a voice assessment."
        case .analyzing: return "The call ended before a voice result was available."
        case .unavailable: return "Voice analysis was unavailable for this call."
        default: return "Recorded voice assessment: " + message
        }
    }
    var message: String {
        if hasCurrentWarning { return "AI-like voice evidence was detected recently. Verify the caller by hanging up and calling a number you already trust. This warning may be wrong." }
        if let qualityReason {
            switch qualityReason {
            case "audio_too_quiet": return "Audio is too quiet for a reliable voice assessment."
            case "audio_too_noisy": return "Background noise prevents a reliable voice assessment."
            case "audio_distorted": return "Audio is distorted. A reliable voice assessment is unavailable."
            default: break
            }
        }
        switch statusReason {
        case "recording_notice_pending": return "Waiting for the recording notice to finish. Voice analysis has not started."
        case "recording_notice_failed": return "The recording notice could not finish. Voice analysis is unavailable."
        case "inference_pending": return "Waiting for the voice analysis result. Your call can continue."
        case "inference_timeout", "inference_failed", "detector_unavailable": return "Voice analysis is unavailable. Your call can continue."
        default: break
        }
        if isStale { return "The previous result describes earlier speech. Waiting for fresh usable caller speech; silence is not human evidence." }
        switch state {
        case .waiting: return "Waiting for enough usable caller speech…"
        case .analyzing: return "Checking the caller’s voice…"
        case .human: return (scoringMethod == "call-evidence-v1" ? "Whole-call voice evidence appears human-like; a current-speech result is not enabled. " : "Voice evidence appears human-like. ") + "This does not verify the caller or mean the call is safe."
        case .ai: return "This voice may be AI-generated. Verify the caller before sharing information."
        case .uncertain: return windows < 2 ? "Not enough usable caller speech yet. Analysis will continue." : "The voice evidence is mixed. Analysis will continue."
        case .unavailable: return "Voice analysis is unavailable. Your call can continue."
        }
    }
    func finalized(at date: Date) -> DeepfakeAssessment {
        guard state == .waiting || state == .analyzing else { return self }
        var result = self
        result = replacing(state: .uncertain, at: date)
        if result.statusReason == nil { result.statusReason = windows == 0 ? "insufficient_speech" : "inference_pending" }
        return result
    }
    func replacing(state: State, at date: Date) -> DeepfakeAssessment {
        var result = DeepfakeAssessment(state: state, updatedAt: date, windows: windows, score: score, recentAI: recentAI,
            currentScore: currentScore, evidenceStart: evidenceStart, evidenceEnd: evidenceEnd,
            evidenceAge: evidenceAge, freshness: freshness, analysisStatus: analysisStatus,
            qualityReason: qualityReason, statusReason: statusReason, currentWarning: currentWarning,
            historicalWarnings: historicalWarnings, pendingState: pendingState, scoringMethod: scoringMethod,
            streamID: streamID, sequence: sequence, windowID: windowID)
        if state == .unavailable { result.analysisStatus = "unavailable" }
        return result
    }
}

/// Strict legacy + cumulative v1 + explicit v2 contract. Transcript risk cannot relabel voice.
struct DeepfakeUpdate: Decodable {
    static let topic = "scam-guard.risk"
    let schema: Int
    let type: String
    let room: String
    let callerIdentity: String
    let streamID: UUID
    let sequence: Int
    let model: String
    let state: DeepfakeAssessment.State?
    let deepfake: Evidence?
    let evidence_version: String?
    let scoring_method: String?
    let window_id: Int?
    let assessment: CurrentEvidence?

    struct Evidence: Decodable {
        let level: String
        let updates: Int
        let human_steps: Int
        let p_last: Double
        let p_smoothed: Double
        let logit_last: Double
        let logit_smoothed: Double
        let method: String?
        let state: DeepfakeAssessment.State?
        let score: Double?
        let score_kind: String?
        let recent_ai: Bool?
    }
    struct CurrentEvidence: Decodable {
        let current_state: DeepfakeAssessment.State
        let current_score: Double?
        let whole_call_score: Double?
        let evidence_start_sec: Double?
        let evidence_end_sec: Double?
        let evidence_age_sec: Double?
        let freshness: String
        let analysis_status: String
        let quality_reason: String?
        let status_reason: String?
        let current_warning: Bool
        let historical_warning_events: [DeepfakeAssessment.WarningEvent]
        let pending_state: DeepfakeAssessment.State?
        let score_kind: String

        var isValid: Bool {
            func score(_ value: Double?) -> Bool { value.map { $0.isFinite && (0...100).contains($0) } ?? true }
            func duration(_ value: Double?) -> Bool { value.map { $0.isFinite && (0...31_536_000).contains($0) } ?? true }
            guard score_kind == "heuristic", score(current_score), score(whole_call_score),
                  duration(evidence_start_sec), duration(evidence_end_sec), duration(evidence_age_sec),
                  ["fresh", "stale", "none"].contains(freshness),
                  ["analyzing", "available", "unavailable", "stale"].contains(analysis_status),
                  quality_reason.map({ ["insufficient_speech", "audio_too_quiet", "audio_too_noisy", "audio_distorted"].contains($0) }) ?? true,
                  status_reason.map({ ["insufficient_speech", "inference_pending", "inference_timeout", "inference_failed", "evidence_stale", "recording_notice_pending", "recording_notice_failed", "detector_unavailable"].contains($0) }) ?? true,
                  historical_warning_events.count <= 64 else { return false }
            if let start = evidence_start_sec, let end = evidence_end_sec { guard end >= start else { return false } }
            else if evidence_start_sec != nil || evidence_end_sec != nil { return false }
            if freshness == "fresh" {
                guard evidence_start_sec != nil, evidence_end_sec != nil, evidence_age_sec != nil,
                      analysis_status == "available" || analysis_status == "unavailable" else { return false }
                if analysis_status == "available" && current_score == nil { return false }
            }
            if current_warning && freshness != "fresh" { return false }
            return historical_warning_events.allSatisfy {
                !$0.id.isEmpty && $0.id.count <= 128 && $0.start_sec.isFinite && $0.start_sec >= 0
                    && $0.end_sec.isFinite && $0.end_sec >= $0.start_sec && $0.end_sec <= 31_536_000
            }
        }
    }
    static func decode(_ data: Data) -> DeepfakeUpdate? {
        guard data.count <= 16_384, let value = try? JSONDecoder().decode(Self.self, from: data),
              value.schema == 1, value.sequence > 0, !value.room.isEmpty, !value.callerIdentity.isEmpty,
              ["real", "stub"].contains(value.model) else { return nil }
        if let window = value.window_id, window < 0 { return nil }
        if let method = value.scoring_method, !["call-evidence-v1", "call-evidence-v2"].contains(method) { return nil }
        if value.assessment != nil || value.evidence_version != nil {
            guard value.evidence_version == "call-evidence-v2", value.assessment?.isValid == true else { return nil }
        }
        if value.scoring_method == "call-evidence-v2", value.assessment == nil { return nil }
        if value.type == "status" {
            guard let state = value.state, [.waiting, .analyzing, .unavailable].contains(state) else { return nil }
        } else if value.type == "risk" {
            guard let e = value.deepfake, ["listening", "elevated", "high"].contains(e.level),
                  e.updates > 0, e.human_steps >= 0, e.human_steps <= e.updates,
                  (0...1).contains(e.p_last), (0...1).contains(e.p_smoothed),
                  e.logit_last.isFinite, e.logit_smoothed.isFinite else { return nil }
            if let method = e.method {
                guard ["call-evidence-v1", "call-evidence-v2"].contains(method), e.score_kind == "heuristic",
                      let score = e.score, score.isFinite, (0...100).contains(score),
                      let state = e.state, [.analyzing, .human, .ai, .uncertain].contains(state),
                      e.recent_ai != nil, state == .analyzing || e.updates >= 2 else { return nil }
                if method == "call-evidence-v2", value.assessment == nil { return nil }
            } else if e.score != nil || e.state != nil || e.score_kind != nil || e.recent_ai != nil { return nil }
        } else { return nil }
        return value
    }
    func assessment(at date: Date) -> DeepfakeAssessment {
        guard model == "real" else { return DeepfakeAssessment(state: .unavailable, updatedAt: date) }
        let e = deepfake
        var result: DeepfakeAssessment.State
        if type != "risk" { result = state ?? .unavailable }
        else if let state = e?.state, e?.method != nil { result = state }
        else if e?.level == "high", (e?.updates ?? 0) >= 3 { result = .ai }
        else if e?.level == "elevated" { result = .uncertain }
        else if e?.level == "listening", (e?.human_steps ?? 0) >= 3 { result = .human }
        else { result = .analyzing }
        let useCurrent = scoring_method == "call-evidence-v2" || e?.method == "call-evidence-v2"
        if useCurrent, let assessment { result = assessment.current_state }
        if assessment?.freshness == "stale" || (assessment?.evidence_age_sec ?? 0) >= DeepfakeAssessment.evidenceFreshnessLimit { result = .uncertain }
        if assessment?.analysis_status == "unavailable" { result = .unavailable }
        return DeepfakeAssessment(state: result, updatedAt: date, windows: e?.updates ?? 0,
            score: assessment?.whole_call_score ?? e?.score, recentAI: e?.recent_ai,
            currentScore: assessment?.current_score, evidenceStart: assessment?.evidence_start_sec,
            evidenceEnd: assessment?.evidence_end_sec, evidenceAge: assessment?.evidence_age_sec,
            freshness: assessment?.freshness, analysisStatus: assessment?.analysis_status,
            qualityReason: assessment?.quality_reason, statusReason: assessment?.status_reason,
            currentWarning: assessment?.current_warning, historicalWarnings: assessment?.historical_warning_events,
            pendingState: assessment?.pending_state, scoringMethod: scoring_method ?? e?.method,
            streamID: streamID, sequence: sequence, windowID: window_id)
    }
}

/// One per call: rejects old sequences/retired streams. Heartbeats do not renew evidence.
struct DeepfakeMonitor {
    static let timeout: TimeInterval = 12
    private var streamID: UUID?
    private var retiredStreams = Set<UUID>()
    private var sequence = 0
    private var lastReceivedTick: TimeInterval?
    private(set) var latest: DeepfakeAssessment?

    mutating func receive(_ update: DeepfakeUpdate, room: String, callerIdentity: String,
                          isAgent: Bool, at date: Date, monotonicTime: TimeInterval? = nil) -> DeepfakeAssessment? {
        guard isAgent, update.room == room, update.callerIdentity == callerIdentity,
              !retiredStreams.contains(update.streamID) else { return nil }
        if streamID != update.streamID {
            if let streamID { retiredStreams.insert(streamID) }
            streamID = update.streamID; sequence = 0
        }
        guard update.sequence > sequence else { return nil }
        sequence = update.sequence
        let assessment = update.assessment(at: date)
        latest = assessment
        lastReceivedTick = monotonicTime ?? date.timeIntervalSinceReferenceDate
        return assessment
    }
    mutating func expire(at date: Date, connectedAt: Date, monotonicTime: TimeInterval? = nil,
                         connectedMonotonicTime: TimeInterval? = nil) -> DeepfakeAssessment? {
        let tick = monotonicTime ?? date.timeIntervalSinceReferenceDate
        let origin = lastReceivedTick ?? connectedMonotonicTime ?? connectedAt.timeIntervalSinceReferenceDate
        let transportElapsed = max(0, tick - origin)
        let elapsed = transportElapsed
        if let latest, latest.freshness == "fresh", let age = latest.evidenceAge,
           age + elapsed >= DeepfakeAssessment.evidenceFreshnessLimit {
            var result = latest.replacing(state: .uncertain, at: date)
            result.freshness = "stale"; result.analysisStatus = "stale"; result.statusReason = "evidence_stale"
            result.evidenceAge = age + elapsed; result.currentWarning = false
            self.latest = result
            return result
        }
        guard transportElapsed >= Self.timeout, latest?.state != .unavailable else { return nil }
        var result = latest?.replacing(state: .unavailable, at: date) ?? DeepfakeAssessment(state: .unavailable, updatedAt: date)
        result.statusReason = "detector_unavailable"
        latest = result
        return result
    }
}

/// Caller-language evidence stays separate from the voice/deepfake result.
struct TranscriptAssessment: Codable, Equatable {
    enum State: String, Codable { case listening, monitoring, stale, unavailable, disabled }
    let state: State
    let updatedAt: Date
    var probability: Double? = nil
    var scoredRevision: Int = 0
    var scoreAge: TimeInterval = 0

    var title: String {
        guard state == .monitoring, let probability else {
            switch state {
            case .listening: return "Listening for caller speech…"
            case .stale: return "Waiting for a fresh transcript result"
            case .disabled: return "Transcript analysis is off"
            default: return "Transcript analysis unavailable"
            }
        }
        return probability >= 0.8 ? "Possible scam language" : "No strong scam-language signal"
    }
    var message: String {
        guard state == .monitoring, let probability else {
            return state == .listening ? "The caller’s words will be checked as they speak." : "Your call can continue."
        }
        return "Scam risk score: \(Int((probability * 100).rounded()))% · update \(scoredRevision)"
    }
    var isWarning: Bool { state == .monitoring && (probability ?? 0) >= 0.8 }
}

struct TranscriptUpdate: Decodable {
    let schema: Int
    let type: String
    let room: String
    let callerIdentity: String
    let streamID: UUID
    let sequence: Int
    let model: String
    let transcript: Evidence

    struct Evidence: Decodable {
        let state: String
        let probability: Double?
        let scored_revision: Int?
        let age_sec: Double?
    }
    static func decode(_ data: Data) -> TranscriptUpdate? {
        guard data.count <= 16_384, let value = try? JSONDecoder().decode(Self.self, from: data),
              value.schema == 1, value.sequence > 0, !value.room.isEmpty, !value.callerIdentity.isEmpty,
              ["risk", "status"].contains(value.type), ["real", "stub"].contains(value.model),
              ["listening", "monitoring", "stale", "disabled", "stt_unavailable", "jev_unavailable", "audio_overrun"].contains(value.transcript.state) else { return nil }
        if value.transcript.state == "monitoring" {
            guard let p = value.transcript.probability, p.isFinite, (0...1).contains(p),
                  let revision = value.transcript.scored_revision, revision > 0,
                  let age = value.transcript.age_sec, age.isFinite, age >= 0 else { return nil }
        }
        return value
    }
    func assessment(at date: Date) -> TranscriptAssessment {
        let evidence = transcript
        let state: TranscriptAssessment.State
        if model != "real" { state = .unavailable }
        else if evidence.state == "monitoring" { state = (evidence.age_sec ?? 16) <= 15 ? .monitoring : .stale }
        else if evidence.state == "listening" { state = .listening }
        else if evidence.state == "stale" { state = .stale }
        else if evidence.state == "disabled" { state = .disabled }
        else { state = .unavailable }
        return TranscriptAssessment(state: state, updatedAt: date,
                                    probability: state == .monitoring ? evidence.probability : nil,
                                    scoredRevision: evidence.scored_revision ?? 0, scoreAge: evidence.age_sec ?? 0)
    }
}

struct TranscriptMonitor {
    private var streamID: UUID?
    private var retiredStreams = Set<UUID>()
    private var sequence = 0
    private(set) var latest: TranscriptAssessment?

    mutating func receive(_ update: TranscriptUpdate, room: String, callerIdentity: String,
                          isAgent: Bool, at date: Date) -> TranscriptAssessment? {
        guard isAgent, update.room == room, update.callerIdentity == callerIdentity,
              !retiredStreams.contains(update.streamID) else { return nil }
        if streamID != update.streamID {
            if let streamID { retiredStreams.insert(streamID) }
            streamID = update.streamID; sequence = 0
        }
        guard update.sequence > sequence else { return nil }
        sequence = update.sequence
        let result = update.assessment(at: date)
        latest = result
        return result
    }
    mutating func expire(at date: Date, connectedAt: Date) -> TranscriptAssessment? {
        let elapsed = date.timeIntervalSince(latest?.updatedAt ?? connectedAt)
        let stale = latest?.state == .monitoring && elapsed + (latest?.scoreAge ?? 0) > 15
        guard (elapsed >= 12 || stale), latest?.state != .unavailable, latest?.state != .stale else { return nil }
        let result = TranscriptAssessment(state: stale ? .stale : .unavailable, updatedAt: date)
        latest = result
        return result
    }
}
