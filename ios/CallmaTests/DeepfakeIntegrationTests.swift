import AVFAudio
import XCTest
@testable import Callma

final class DeepfakeIntegrationTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    private func fixtureObjects() throws -> [[String: Any]] {
        try ["deepfake-wire", "deepfake-presentation"].flatMap { name in
            let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: "json"))
            let root = try XCTUnwrap(try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
            return try XCTUnwrap(root["cases"] as? [[String: Any]])
        }
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
            let value = update.assessment(at: now)
            XCTAssertEqual(value.state.rawValue, item["expected"] as? String, item["name"] as? String ?? "")
            if let title = item["expected_title"] as? String { XCTAssertEqual(value.title, title) }
            if value.hasCurrentWarning {
                XCTAssertNotEqual(value.voice, .human)
                XCTAssertEqual(value.title, "AI-like voice detected recently")
                XCTAssertFalse(value.message.contains("appears human"))
            }
        }
    }
    func testWarningPendingHistoryAndQualityPresentation() throws {
        let warning = try decode(payload(named: "human_plus_warning")).assessment(at: now)
        XCTAssertEqual(warning.state, .human) // presentation fix is not a classification change
        XCTAssertEqual(warning.voice, .unknown)
        XCTAssertEqual(warning.title, "AI-like voice detected recently")
        XCTAssertTrue(warning.message.contains("number you already trust"))
        let pending = try decode(payload(named: "pending_65_6")).assessment(at: now)
        XCTAssertEqual(pending.state, .uncertain)
        XCTAssertTrue(pending.scoreText.contains("65.6/100"))
        XCTAssertTrue(pending.scoreText.contains("Whole-call evidence"))
        XCTAssertNotNil(pending.pendingMessage)
        let recovered = try decode(payload(named: "v2_actual_recovered")).assessment(at: now)
        XCTAssertEqual(recovered.voice, .human)
        XCTAssertFalse(recovered.hasCurrentWarning)
        XCTAssertFalse(try XCTUnwrap(recovered.historicalWarnings).isEmpty)
        XCTAssertTrue(recovered.historyMessage.contains("Recorded"))
        for name in ["quality_audio_too_quiet", "quality_audio_too_noisy", "quality_audio_distorted", "quality_insufficient_speech"] {
            let value = try decode(payload(named: name)).assessment(at: now)
            XCTAssertNotEqual(value.voice, .human)
            XCTAssertNotEqual(value.voice, .ai)
        }
    }
    func testInvalidV2CannotRelabelVoiceAndFreshnessIsNotHeartbeatReceipt() throws {
        let valid = try payload(named: "v2_actual_recovered")
        for field in ["evidence_start_sec", "evidence_end_sec", "evidence_age_sec"] {
            var object = valid
            var assessment = try XCTUnwrap(object["assessment"] as? [String: Any])
            assessment[field] = -1
            object["assessment"] = assessment
            XCTAssertNil(DeepfakeUpdate.decode(try JSONSerialization.data(withJSONObject: object)))
        }
        var monitor = DeepfakeMonitor()
        var value = valid
        var evidence = try XCTUnwrap(value["assessment"] as? [String: Any])
        evidence["evidence_age_sec"] = 19.0
        value["assessment"] = evidence
        let update = try decode(value)
        _ = monitor.receive(update, room: update.room, callerIdentity: update.callerIdentity, isAgent: true,
                            at: now, monotonicTime: 100)
        let stale = monitor.expire(at: now.addingTimeInterval(-500), connectedAt: now, monotonicTime: 101)
        XCTAssertEqual(stale?.freshness, "stale")
        XCTAssertNotEqual(stale?.voice, .human)
        XCTAssertEqual(monitor.expire(at: now.addingTimeInterval(-500), connectedAt: now, monotonicTime: 112)?.state, .unavailable)
    }
    func testInitialDeadlineStartsAtConnectionAndLateResultRecovers() throws {
        var session = PhoneSessionState()
        let id = UUID()
        _ = session.begin(PhoneCall(id: id, person: PhoneNumber.person("+13125550123"), direction: .incoming,
                                   createdAt: now.addingTimeInterval(-60), stage: .incoming))
        session.connected(id: id, at: now, monotonicTime: 100)
        session.finalizeInitialAssessment(id: id, at: now.addingTimeInterval(14.999), monotonicTime: 114.999)
        XCTAssertEqual(session.current?.deepfake?.state, .analyzing)
        session.finalizeInitialAssessment(id: id, at: now.addingTimeInterval(15), monotonicTime: 115)
        XCTAssertEqual(session.current?.deepfake?.state, .uncertain)
        XCTAssertEqual(session.current?.deepfake?.statusReason, "insufficient_speech")
        let late = DeepfakeAssessment(state: .human, updatedAt: now.addingTimeInterval(16), windows: 3, score: 12)
        session.assessDeepfake(id: id, assessment: late)
        session.recordVoiceDisplay(id: id, monotonicTime: 116.5)
        XCTAssertEqual(session.current?.voice, .human)
        XCTAssertEqual(session.current?.analysisTiming.last?.elapsedSeconds, 16.5)
    }
    @MainActor
    func testActualCoordinatorDeadlineDuringNoticeAndLateRecovery() async throws {
        let backend = TranscriptTestBackend()
        let coordinator = PhoneCallCoordinator(backend: backend, microphonePermission: { true })
        let id = UUID(), connectedAt = Date()
        backend.onEvent?(.incoming(id, "+13125550123", nil))
        backend.onEvent?(.connected(id, connectedAt))
        let object = try payload(named: "status_recording_notice_pending")
        backend.onEvent?(.deepfakeAssessment(id, try decode(object).assessment(at: connectedAt)))
        try await Task.sleep(nanoseconds: 15_200_000_000)
        XCTAssertEqual(coordinator.active?.deepfake?.state, .uncertain)
        XCTAssertEqual(coordinator.active?.deepfake?.statusReason, "recording_notice_pending")
        XCTAssertEqual(coordinator.active?.analysisTiming.first?.event, "connected")
        XCTAssertTrue(coordinator.active?.analysisTiming.contains { $0.event == "initial_deadline" && $0.elapsedSeconds >= 15 } == true)
        backend.onEvent?(.deepfakeAssessment(id, DeepfakeAssessment(state: .human, updatedAt: Date(), windows: 3)))
        XCTAssertEqual(coordinator.active?.voice, .human)
        backend.onEvent?(.ended(id, .completed, Date()))
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
        XCTAssertNil(DeepfakeUpdate.decode(Data(repeating: 32, count: 16_385)))
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
        session.assessDeepfake(id: id, assessment: DeepfakeAssessment(state: .unavailable, updatedAt: now.addingTimeInterval(6)))
        XCTAssertEqual(session.current?.voice, .unknown)
        XCTAssertEqual(session.current?.lastDeepfakeResult, assessment)
        let record = session.finish(id: id, outcome: .completed, at: now.addingTimeInterval(8))
        XCTAssertEqual(record?.voice, .ai)
        XCTAssertEqual(record?.deepfake, assessment)
        session.assessDeepfake(id: id, assessment: assessment)
        XCTAssertNil(session.current)
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
