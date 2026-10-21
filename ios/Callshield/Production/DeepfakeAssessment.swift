import Foundation

/// Voice evidence is separate from transcript/scam risk. No audio is stored.
struct DeepfakeAssessment: Codable, Equatable {
    enum State: String, Codable { case waiting, analyzing, human, ai, uncertain, unavailable }
    let state: State
    let updatedAt: Date
    var windows: Int = 0
    /// Threshold-relative AI evidence, 0...100. Not a calibrated probability.
    var score: Double? = nil
    var recentAI: Bool? = nil

    static let initialDeadline: TimeInterval = 15

    var title: String {
        switch state {
        case .waiting, .analyzing: return "Analyzing"
        case .human: return "Human"
        case .ai: return "Likely AI"
        case .uncertain: return "Inconclusive"
        case .unavailable: return "Analysis unavailable"
        }
    }
    var scoreText: String {
        if let score { return "AI score: \(Int(score.rounded()))/100" }
        return state == .waiting || state == .analyzing ? "Gathering voice evidence…" : "AI score unavailable"
    }
    func finalized(at date: Date) -> DeepfakeAssessment {
        guard state == .waiting || state == .analyzing else { return self }
        return DeepfakeAssessment(state: .uncertain, updatedAt: date, windows: windows,
                                  score: score, recentAI: recentAI)
    }

    var voice: Voice {
        switch state {
        case .human: return .human
        case .ai: return .ai
        case .waiting, .analyzing: return .analyzing
        default: return .unknown
        }
    }
    var historyMessage: String {
        switch state {
        case .waiting: return "Not enough caller speech for a voice assessment."
        case .analyzing: return "The call ended before a voice result was available."
        case .unavailable: return "Voice analysis was unavailable for this call."
        default: return message
        }
    }
    var message: String {
        switch state {
        case .waiting: return "Waiting for enough caller speech…"
        case .analyzing: return "Checking the caller’s voice…"
        case .human: return "This voice appears to be human."
        case .ai: return "This voice may be AI-generated. Verify the caller before sharing information."
        case .uncertain: return windows < 2 ? "Not enough usable caller speech yet. Analysis will continue." : "The voice evidence is mixed. Analysis will continue."
        case .unavailable: return "Voice analysis is unavailable. Your call can continue."
        }
    }
}

/// Versioned contract produced by LiveKit Setup/risk_protocol.py. Strict decoding keeps
/// malformed data, stub scores and the combined transcript level out of voice labels.
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

    static func decode(_ data: Data) -> DeepfakeUpdate? {
        guard data.count <= 16_384, let value = try? JSONDecoder().decode(Self.self, from: data),
              value.schema == 1, value.sequence > 0, !value.room.isEmpty, !value.callerIdentity.isEmpty,
              ["real", "stub"].contains(value.model) else { return nil }
        if value.type == "status" {
            guard let state = value.state, [.waiting, .analyzing, .unavailable].contains(state) else { return nil }
        } else if value.type == "risk" {
            guard let e = value.deepfake, ["listening", "elevated", "high"].contains(e.level),
                  e.updates > 0, e.human_steps >= 0, e.human_steps <= e.updates,
                  (0...1).contains(e.p_last), (0...1).contains(e.p_smoothed),
                  e.logit_last.isFinite, e.logit_smoothed.isFinite else { return nil }
            if let method = e.method {
                guard method == "call-evidence-v1", e.score_kind == "heuristic",
                      let score = e.score, score.isFinite, (0...100).contains(score),
                      let state = e.state, [.analyzing, .human, .ai, .uncertain].contains(state),
                      e.recent_ai != nil,
                      state == .analyzing || e.updates >= 2 else { return nil }
            } else if e.score != nil || e.state != nil || e.score_kind != nil || e.recent_ai != nil {
                return nil
            }
        } else { return nil }
        return value
    }

    func assessment(at date: Date) -> DeepfakeAssessment {
        guard model == "real" else { return DeepfakeAssessment(state: .unavailable, updatedAt: date) }
        guard type == "risk", let e = deepfake else {
            return DeepfakeAssessment(state: state ?? .unavailable, updatedAt: date)
        }
        let result: DeepfakeAssessment.State
        if e.method == "call-evidence-v1", let state = e.state {
            return DeepfakeAssessment(state: state, updatedAt: date, windows: e.updates,
                                      score: e.score, recentAI: e.recent_ai)
        }
        if e.level == "high", e.updates >= 3 { result = .ai }
        else if e.level == "elevated" { result = .uncertain }
        else if e.level == "listening", e.human_steps >= 3 { result = .human }
        else { result = .analyzing }
        return DeepfakeAssessment(state: result, updatedAt: date, windows: e.updates)
    }
}

/// One per call; rejects duplicate/out-of-order messages and retired agent streams,
/// and expires results when heartbeats stop.
struct DeepfakeMonitor {
    static let timeout: TimeInterval = 12
    private var streamID: UUID?
    private var retiredStreams = Set<UUID>()
    private var sequence = 0
    private(set) var latest: DeepfakeAssessment?

    mutating func receive(_ update: DeepfakeUpdate, room: String, callerIdentity: String,
                          isAgent: Bool, at date: Date) -> DeepfakeAssessment? {
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
        return assessment
    }

    mutating func expire(at date: Date, connectedAt: Date) -> DeepfakeAssessment? {
        guard date.timeIntervalSince(latest?.updatedAt ?? connectedAt) >= Self.timeout,
              latest?.state != .unavailable else { return nil }
        let assessment = DeepfakeAssessment(state: .unavailable, updatedAt: date)
        latest = assessment
        return assessment
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
