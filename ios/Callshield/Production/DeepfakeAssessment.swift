import Foundation

/// Voice evidence is separate from transcript/scam risk. No audio is stored.
struct DeepfakeAssessment: Codable, Equatable {
    enum State: String, Codable { case waiting, analyzing, human, ai, uncertain, unavailable }
    let state: State
    let updatedAt: Date
    var windows: Int = 0

    var voice: Voice {
        switch state {
        case .human: return .human
        case .ai: return .ai
        case .analyzing: return .analyzing
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
        case .uncertain: return "The voice result is uncertain. Keep listening."
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
        } else { return nil }
        return value
    }

    func assessment(at date: Date) -> DeepfakeAssessment {
        guard model == "real" else { return DeepfakeAssessment(state: .unavailable, updatedAt: date) }
        guard type == "risk", let e = deepfake else {
            return DeepfakeAssessment(state: state ?? .unavailable, updatedAt: date)
        }
        let result: DeepfakeAssessment.State
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
