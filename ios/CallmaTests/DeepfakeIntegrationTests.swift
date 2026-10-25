import AVFAudio
import XCTest
@testable import Callma

final class DeepfakeIntegrationTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    private func fixtureObjects() throws -> [[String: Any]] {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "deepfake-wire", withExtension: "json"))
        let root = try XCTUnwrap(try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        return try XCTUnwrap(root["cases"] as? [[String: Any]])
    }
    private func payload(named name: String) throws -> [String: Any] {
        let item = try XCTUnwrap(try fixtureObjects().first { $0["name"] as? String == name })
        return try XCTUnwrap(item["payload"] as? [String: Any])
    }
    private func decode(_ object: [String: Any]) throws -> DeepfakeUpdate {
        try XCTUnwrap(DeepfakeUpdate.decode(JSONSerialization.data(withJSONObject: object)))
    }

    func testPythonRiskEngineFixturesDriveEveryVoiceState() throws {
        for item in try fixtureObjects() {
            let update = try decode(XCTUnwrap(item["payload"] as? [String: Any]))
            XCTAssertEqual(update.assessment(at: now).state.rawValue, item["expected"] as? String, item["name"] as? String ?? "")
        }
    }
    func testMalformedMessagesCannotBecomeVoiceLabels() throws {
        let complete = try payload(named: "high")
        for key in ["schema", "type", "room", "callerIdentity", "streamID", "sequence", "model", "deepfake"] {
            var object = complete; object[key] = nil
            XCTAssertNil(DeepfakeUpdate.decode(try JSONSerialization.data(withJSONObject: object)), key)
        }
        for (key, value) in [("schema", 2), ("sequence", 0)] {
            var object = complete; object[key] = value
            XCTAssertNil(DeepfakeUpdate.decode(try JSONSerialization.data(withJSONObject: object)))
        }
        var object = complete
        var evidence = try XCTUnwrap(object["deepfake"] as? [String: Any])
        evidence["p_smoothed"] = 1.1; object["deepfake"] = evidence
        XCTAssertNil(DeepfakeUpdate.decode(try JSONSerialization.data(withJSONObject: object)))
        var status = try payload(named: "waiting"); status["state"] = "human"
        XCTAssertNil(DeepfakeUpdate.decode(try JSONSerialization.data(withJSONObject: status)))
        XCTAssertNil(DeepfakeUpdate.decode(Data("not json".utf8)))
        XCTAssertNil(DeepfakeUpdate.decode(Data(repeating: 32, count: 32_769)))
    }
    func testScopeOrderingRestartAndTimeoutRecovery() throws {
        var monitor = DeepfakeMonitor()
        let object = try payload(named: "high")
        let update = try decode(object)
        func receive(_ value: DeepfakeUpdate, room: String = "call-test", caller: String = "sip-test", agent: Bool = true) -> DeepfakeAssessment? {
            monitor.receive(value, room: room, callerIdentity: caller, isAgent: agent, at: now)
        }
        XCTAssertNil(receive(update, room: "other-call"))
        XCTAssertNil(receive(update, caller: "other-caller"))
        XCTAssertNil(receive(update, agent: false))
        XCTAssertEqual(receive(update)?.voice, .ai)
        XCTAssertNil(receive(update))
        XCTAssertNil(receive(try decode(payload(named: "human"))))
        XCTAssertNil(monitor.expire(at: now.addingTimeInterval(11), connectedAt: now))
        XCTAssertEqual(monitor.expire(at: now.addingTimeInterval(12), connectedAt: now)?.state, .unavailable)
        var restart = object; restart["streamID"] = UUID().uuidString; restart["sequence"] = 1
        XCTAssertEqual(receive(try decode(restart))?.voice, .ai)
        var stale = object; stale["sequence"] = 100
        XCTAssertNil(receive(try decode(stale)))
    }
    func testNoMessagesTimesOutAndUnansweredOrStaleResultsAreIgnored() {
        var monitor = DeepfakeMonitor()
        XCTAssertEqual(monitor.expire(at: now.addingTimeInterval(12), connectedAt: now)?.state, .unavailable)
        var session = PhoneSessionState()
        let id = UUID(), other = UUID()
        let person = PhoneNumber.person("+13125550123")
        let assessment = DeepfakeAssessment(state: .ai, updatedAt: now, windows: 3)
        _ = session.begin(PhoneCall(id: id, person: person, direction: .incoming, createdAt: now, stage: .incoming))
        session.assessDeepfake(id: id, assessment: assessment)
        XCTAssertNil(session.current?.deepfake)
        session.connected(id: id, at: now)
        session.assessDeepfake(id: other, assessment: assessment)
        XCTAssertEqual(session.current?.deepfake?.state, .analyzing)
        session.assessDeepfake(id: id, assessment: assessment)
        XCTAssertEqual(session.current?.voice, .ai)
        session.assessDeepfake(id: id, assessment: DeepfakeAssessment(state: .waiting, updatedAt: now.addingTimeInterval(5)))
        XCTAssertEqual(session.current?.voice, .ai)
        session.assessDeepfake(id: id, assessment: DeepfakeAssessment(state: .unavailable, updatedAt: now.addingTimeInterval(6)))
        XCTAssertEqual(session.current?.voice, .unknown)
        XCTAssertEqual(session.current?.lastDeepfakeResult, assessment)
        let record = session.finish(id: id, outcome: .completed, at: now.addingTimeInterval(8))
        XCTAssertEqual(record?.voice, .ai)
        XCTAssertEqual(record?.deepfake, assessment)
        session.assessDeepfake(id: id, assessment: assessment)
        XCTAssertNil(session.current)
    }
    func testVoiceEvidenceStillDecodesAlongsideBoundedUnicodeExcerpt() throws {
        var message = try payload(named: "high")
        message["transcript"] = ["state": "monitoring", "probability": 0.95,
                                 "scored_revision": 1, "age_sec": 0,
                                 "saved_excerpt": String(repeating: "😀", count: 6000)]
        let data = try JSONSerialization.data(withJSONObject: message)
        XCTAssertLessThanOrEqual(data.count, 32_768)
        XCTAssertEqual(DeepfakeUpdate.decode(data)?.assessment(at: now).voice, .ai)
        XCTAssertEqual(TranscriptUpdate.decode(data)?.assessment(at: now).savedExcerpt?.count, 6000)
    }

    func testWaitingShowsAnalyzingAndContinuousInconclusiveEvidenceEndsByThirtySeconds() throws {
        let waiting = try payload(named: "waiting")
        var monitor = DeepfakeMonitor()
        XCTAssertEqual(try decode(waiting).assessment(at: now).voice, .analyzing)
        for second in stride(from: 0, through: 32, by: 2) {
            var message = waiting
            message["sequence"] = second + 1
            let result = monitor.receive(try decode(message), room: "call-test", callerIdentity: "sip-test", isAgent: true,
                                         at: now.addingTimeInterval(Double(second)))
            XCTAssertEqual(result?.state, second < 30 ? .waiting : .uncertain)
        }
    }

    func testPauseDoesNotReplaceResolvedVoiceWithDeadlineUncertainty() throws {
        var monitor = DeepfakeMonitor()
        _ = monitor.receive(try decode(payload(named: "high")), room: "call-test", callerIdentity: "sip-test", isAgent: true, at: now)
        var waiting = try payload(named: "waiting")
        waiting["sequence"] = 100
        let result = monitor.receive(try decode(waiting), room: "call-test", callerIdentity: "sip-test", isAgent: true, at: now.addingTimeInterval(32))
        XCTAssertEqual(result?.state, .waiting)
        XCTAssertNil(monitor.expire(at: now.addingTimeInterval(32), connectedAt: now))
    }

    func testSavedHistoryRemainsCompatibleWithOldRecords() throws {
        let assessment = DeepfakeAssessment(state: .human, updatedAt: now, windows: 3)
        let record = PhoneCallRecord(id: UUID(), person: PhoneNumber.person("+13125550123"), date: now,
                                    duration: 12, direction: .incoming, outcome: .completed, voice: .human, deepfake: assessment)
        let data = try JSONEncoder().encode(record)
        XCTAssertEqual(try JSONDecoder().decode(PhoneCallRecord.self, from: data), record)
        var old = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        old["deepfake"] = nil
        let decoded = try JSONDecoder().decode(PhoneCallRecord.self, from: JSONSerialization.data(withJSONObject: old))
        XCTAssertNil(decoded.deepfake)
        XCTAssertEqual(decoded.voice, .human)
    }

    func testFifteenSecondDeadlineUsesCallConnectionNotSpeechDuration() {
        var session = PhoneSessionState()
        let id = UUID()
        _ = session.begin(PhoneCall(id: id, person: PhoneNumber.person("+13125550123"),
                                   direction: .incoming, createdAt: now.addingTimeInterval(-40), stage: .incoming))
        session.connected(id: id, at: now)
        XCTAssertEqual(session.current?.deepfake?.title, "Analyzing")
        session.finalizeInitialAssessment(id: id, at: now.addingTimeInterval(14.999))
        XCTAssertEqual(session.current?.deepfake?.state, .analyzing)
        session.finalizeInitialAssessment(id: id, at: now.addingTimeInterval(15))
        XCTAssertEqual(session.current?.deepfake?.title, "Inconclusive")
        XCTAssertNil(session.current?.deepfake?.score)
        // Late warm-up heartbeats cannot bring Analyzing back after the deadline.
        session.assessDeepfake(id: id, assessment: DeepfakeAssessment(state: .analyzing, updatedAt: now.addingTimeInterval(16), windows: 1, score: 10))
        XCTAssertEqual(session.current?.deepfake?.state, .uncertain)
        XCTAssertEqual(session.current?.deepfake?.score, 10)
        session.assessDeepfake(id: id, assessment: DeepfakeAssessment(state: .human, updatedAt: now.addingTimeInterval(20), windows: 2, score: 12))
        XCTAssertEqual(session.current?.deepfake?.title, "Human")
        XCTAssertEqual(session.current?.deepfake?.scoreText, "AI score: 12/100")
    }

    func testDeadlineAndPauseDoNotEraseAnEarlyVerdictOrScore() {
        var session = PhoneSessionState()
        let id = UUID()
        _ = session.begin(PhoneCall(id: id, person: PhoneNumber.person("+13125550123"),
                                   direction: .incoming, createdAt: now, stage: .incoming))
        session.connected(id: id, at: now)
        let early = DeepfakeAssessment(state: .ai, updatedAt: now.addingTimeInterval(9), windows: 2, score: 87, recentAI: true)
        session.assessDeepfake(id: id, assessment: early)
        session.finalizeInitialAssessment(id: id, at: now.addingTimeInterval(15))
        XCTAssertEqual(session.current?.deepfake, early)
        session.assessDeepfake(id: id, assessment: DeepfakeAssessment(state: .waiting, updatedAt: now.addingTimeInterval(25)))
        XCTAssertEqual(session.current?.deepfake, early)
        XCTAssertEqual(session.finish(id: id, outcome: .completed, at: now.addingTimeInterval(30))?.deepfake, early)
        session.finalizeInitialAssessment(id: id, at: now.addingTimeInterval(31))
        XCTAssertNil(session.current)
    }

    func testCumulativeContractRejectsMissingAndOutOfRangeScoreFields() throws {
        let object = try payload(named: "cumulative_ai")
        let e = try XCTUnwrap(object["deepfake"] as? [String: Any])
        for key in ["score", "score_kind", "state", "recent_ai", "method"] {
            var invalid = object, evidence = e
            evidence[key] = nil; invalid["deepfake"] = evidence
            XCTAssertNil(DeepfakeUpdate.decode(try JSONSerialization.data(withJSONObject: invalid)), key)
        }
        for score in [-1.0, 101.0] {
            var invalid = object, evidence = e
            evidence["score"] = score; invalid["deepfake"] = evidence
            XCTAssertNil(DeepfakeUpdate.decode(try JSONSerialization.data(withJSONObject: invalid)))
        }
        let result = try decode(object).assessment(at: now)
        XCTAssertEqual(result.title, "Likely AI")
        XCTAssertNotNil(result.score)
        let data = try JSONEncoder().encode(result)
        XCTAssertEqual(try JSONDecoder().decode(DeepfakeAssessment.self, from: data), result)
    }

    @MainActor
    func testCoordinatorActuallySchedulesDeadlineAndLateEvidenceRecovers() async throws {
        let backend = TranscriptTestBackend()
        let store = ProductionStore(repository: MemoryPhoneRepository(), backend: backend)
        let id = UUID(), connectedAt = Date().addingTimeInterval(-15)
        backend.onEvent?(.incoming(id, "+13125550123", nil))
        backend.onEvent?(.connected(id, connectedAt))
        // An already-due connection exercises the real scheduled task without a 15s test delay.
        for _ in 0..<100 {
            if store.active?.deepfake?.state == .uncertain { break }
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertEqual(store.active?.deepfake?.state, .uncertain)
        XCTAssertNil(store.active?.deepfake?.score)
        backend.onEvent?(.deepfakeAssessment(id, DeepfakeAssessment(state: .human, updatedAt: Date(), windows: 2, score: 12)))
        XCTAssertEqual(store.active?.deepfake?.title, "Human")
        XCTAssertEqual(store.active?.deepfake?.score, 12)
        backend.onEvent?(.ended(id, .completed, Date()))
        XCTAssertEqual(store.history.first?.deepfake?.score, 12)
    }

    @MainActor
    func testHistoryRefreshPreservesDetectorEvidence() {
        let repository = MemoryPhoneRepository()
        let store = ProductionStore(repository: repository)
        let id = UUID(), person = PhoneNumber.person("+13125550123")
        let assessment = DeepfakeAssessment(state: .ai, updatedAt: now, windows: 3)
        let checked = PhoneCallRecord(id: id, person: person, date: now, duration: 8,
                                     direction: .incoming, outcome: .completed, voice: .ai, deepfake: assessment)
        store.mergeHistory([checked])
        store.mergeHistory([PhoneCallRecord(id: id, person: person, date: now, duration: 8,
                                           direction: .incoming, outcome: .completed, voice: .unknown)])
        XCTAssertEqual(store.history.first?.deepfake, assessment)
        XCTAssertEqual(store.history.first?.voice, .ai)
        XCTAssertEqual(repository.snapshot.history.first?.deepfake, assessment)
    }
}


final class TranscriptIntegrationTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)
    private func object(_ state: String = "monitoring", probability: Double = 0.91, age: Double = 1) -> [String: Any] {
        ["schema": 1, "type": "status", "state": "unavailable", "room": "call-test", "callerIdentity": "sip-test",
         "streamID": "01010101-0101-0101-0101-010101010101", "sequence": 1, "model": "real",
         "transcript": ["state": state, "probability": probability, "scored_revision": 12, "age_sec": age]]
    }
    private func decode(_ object: [String: Any]) throws -> TranscriptUpdate {
        try XCTUnwrap(TranscriptUpdate.decode(JSONSerialization.data(withJSONObject: object)))
    }
    func testTranscriptRunsEvenWhenVoiceIsUnavailableAndRejectsInvalidProbabilities() throws {
        let update = try decode(object())
        XCTAssertEqual(update.assessment(at: now).probability, 0.91)
        XCTAssertTrue(update.assessment(at: now).isWarning)
        XCTAssertEqual(update.assessment(at: now).scoredRevision, 12)
        for probability in [-0.1, 1.1] {
            XCTAssertNil(TranscriptUpdate.decode(try JSONSerialization.data(withJSONObject: object(probability: probability))))
        }
        for state in ["stt_unavailable", "jev_unavailable", "audio_overrun"] {
            XCTAssertEqual(try decode(object(state)).assessment(at: now).state, .unavailable)
            XCTAssertNil(try decode(object(state)).assessment(at: now).probability)
        }
        var stub = object(); stub["model"] = "stub"
        XCTAssertEqual(try decode(stub).assessment(at: now).state, .unavailable)
        XCTAssertEqual(try decode(object(age: 16)).assessment(at: now).state, .stale)
    }
    func testScopeOrderingRestartAndStaleScoreExpiration() throws {
        var monitor = TranscriptMonitor()
        let first = try decode(object(age: 14))
        XCTAssertNil(monitor.receive(first, room: "other", callerIdentity: "sip-test", isAgent: true, at: now))
        XCTAssertNil(monitor.receive(first, room: "call-test", callerIdentity: "sip-test", isAgent: false, at: now))
        XCTAssertNotNil(monitor.receive(first, room: "call-test", callerIdentity: "sip-test", isAgent: true, at: now))
        XCTAssertNil(monitor.receive(first, room: "call-test", callerIdentity: "sip-test", isAgent: true, at: now))
        XCTAssertEqual(monitor.expire(at: now.addingTimeInterval(2), connectedAt: now)?.state, .stale)
        var restart = object(); restart["streamID"] = UUID().uuidString
        XCTAssertNotNil(monitor.receive(try decode(restart), room: "call-test", callerIdentity: "sip-test", isAgent: true, at: now))
        var old = object(); old["sequence"] = 100
        XCTAssertNil(monitor.receive(try decode(old), room: "call-test", callerIdentity: "sip-test", isAgent: true, at: now))
    }
    func testPeakRiskPersistsAcrossLowerScoresAndFailuresAndResetsForNextCall() throws {
        var session = PhoneSessionState()
        let person = PhoneNumber.person("+13125550123"), id = UUID()
        _ = session.begin(PhoneCall(id: id, person: person, direction: .incoming, createdAt: now, stage: .incoming))
        session.connected(id: id, at: now)
        XCTAssertEqual(session.current?.voice, .analyzing)
        for probability in [0.62, 0.08, 0.91, 0.12] {
            session.assessTranscript(id: id, assessment: TranscriptAssessment(state: .monitoring, updatedAt: now, probability: probability))
        }
        XCTAssertEqual(session.current?.transcript?.probability, 0.91)
        session.assessTranscript(id: id, assessment: TranscriptAssessment(state: .unavailable, updatedAt: now))
        XCTAssertEqual(session.current?.transcript?.state, .unavailable)
        XCTAssertEqual(session.finish(id: id, outcome: .completed, at: now)?.transcript?.probability, 0.91)
        let next = UUID()
        _ = session.begin(PhoneCall(id: next, person: person, direction: .incoming, createdAt: now, stage: .incoming))
        session.connected(id: next, at: now)
        session.assessTranscript(id: next, assessment: TranscriptAssessment(state: .monitoring, updatedAt: now, probability: 0.08))
        XCTAssertEqual(session.current?.transcript?.probability, 0.08)
    }
    func testSavedExcerptDecodesAndSurvivesCallEndAndOlderRecords() throws {
        var payload = object()
        var evidence = try XCTUnwrap(payload["transcript"] as? [String: Any])
        evidence["saved_excerpt"] = "Please read me your bank code."
        payload["transcript"] = evidence
        let assessment = try decode(payload).assessment(at: now)
        XCTAssertEqual(assessment.savedExcerpt, "Please read me your bank code.")
        XCTAssertNil(try decode(object()).assessment(at: now).savedExcerpt)
        var session = PhoneSessionState()
        let id = UUID(), person = PhoneNumber.person("+13125550123")
        _ = session.begin(PhoneCall(id: id, person: person, direction: .incoming, createdAt: now, stage: .incoming))
        session.connected(id: id, at: now)
        session.assessTranscript(id: id, assessment: assessment)
        session.assessTranscript(id: id, assessment: TranscriptAssessment(state: .monitoring, updatedAt: now, probability: 0.1))
        let record = try XCTUnwrap(session.finish(id: id, outcome: .completed, at: now))
        XCTAssertEqual(record.transcript?.savedExcerpt, assessment.savedExcerpt)
        XCTAssertEqual(try JSONDecoder().decode(PhoneCallRecord.self, from: JSONEncoder().encode(record)), record)

        evidence["saved_excerpt"] = String(repeating: "x", count: 6001)
        payload["transcript"] = evidence
        XCTAssertNil(TranscriptUpdate.decode(try JSONSerialization.data(withJSONObject: payload)))
    }

    func testTranscriptCannotRelabelVoiceAndHistoryRemainsBackwardCompatible() throws {
        var session = PhoneSessionState()
        let id = UUID(), person = PhoneNumber.person("+13125550123")
        let result = TranscriptAssessment(state: .monitoring, updatedAt: now, probability: 0.93, scoredRevision: 5)
        _ = session.begin(PhoneCall(id: id, person: person, direction: .incoming, createdAt: now, stage: .incoming))
        session.assessTranscript(id: id, assessment: result)
        XCTAssertNil(session.current?.transcript)
        session.connected(id: id, at: now)
        session.assessTranscript(id: UUID(), assessment: result)
        XCTAssertNil(session.current?.transcript)
        session.assessDeepfake(id: id, assessment: DeepfakeAssessment(state: .human, updatedAt: now, windows: 3))
        session.assessTranscript(id: id, assessment: result)
        XCTAssertEqual(session.current?.voice, .human)
        session.assessTranscript(id: id, assessment: TranscriptAssessment(state: .unavailable, updatedAt: now))
        let record = try XCTUnwrap(session.finish(id: id, outcome: .completed, at: now.addingTimeInterval(10)))
        XCTAssertEqual(record.transcript, result)
        XCTAssertEqual(try JSONDecoder().decode(PhoneCallRecord.self, from: JSONEncoder().encode(record)), record)
        var old = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(record)) as? [String: Any])
        old["transcript"] = nil
        XCTAssertNil(try JSONDecoder().decode(PhoneCallRecord.self, from: JSONSerialization.data(withJSONObject: old)).transcript)
    }

    @MainActor
    func testCoordinatorRoutesTranscriptAndHistoryRefreshPreservesIt() async throws {
        let backend = TranscriptTestBackend()
        let store = ProductionStore(repository: MemoryPhoneRepository(), backend: backend)
        let id = UUID()
        backend.onEvent?(.incoming(id, "+13125550123", nil))
        backend.onEvent?(.connected(id, now))
        let assessment = TranscriptAssessment(state: .monitoring, updatedAt: now, probability: 0.94, scoredRevision: 8)
        backend.onEvent?(.transcriptAssessment(id, assessment))
        XCTAssertEqual(store.active?.transcript, assessment)
        backend.onEvent?(.ended(id, .completed, now.addingTimeInterval(5)))
        XCTAssertEqual(store.history.first?.transcript, assessment)
        let record = try XCTUnwrap(store.history.first)
        store.mergeHistory([PhoneCallRecord(id: id, person: record.person, date: now, duration: 5,
                                            direction: .incoming, outcome: .completed, voice: .unknown)])
        XCTAssertEqual(store.history.first?.transcript, assessment)
    }
}

@MainActor private final class TranscriptTestBackend: CallingBackend {
    var isConfigured: Bool { true }
    var usesVoIPPush: Bool { false }
    var canPlaceOutgoingCalls: Bool { false }
    var supportsHoldAndKeypad: Bool { false }
    var onEvent: ((CallingEvent) -> Void)?
    func listenForIncomingCalls() {}
    func start(callID: UUID, number: String) async throws {}
    func prepareIncoming(callID: UUID, number: String) async throws {}
    func answer(callID: UUID) async throws {}
    func end(callID: UUID) async throws {}
    func setMuted(_ muted: Bool, callID: UUID) async throws {}
    func setHeld(_ held: Bool, callID: UUID) async throws {}
    func sendDTMF(_ digits: String, callID: UUID) async throws {}
    func registerVoIPToken(_ token: Data?) async throws {}
    func activateAudio(_ session: AVAudioSession) {}
    func deactivateAudio(_ session: AVAudioSession) {}
    func reset() {}
}
