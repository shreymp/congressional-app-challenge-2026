import XCTest
@testable import Callshield

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
        XCTAssertNil(session.current?.deepfake)
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
