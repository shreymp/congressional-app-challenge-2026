// Foundation-only checks against the production sources. No iOS SDK or model needed.
import Foundation

@main
struct DeepfakeContractCheck {
    static func main() throws {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        var cases: [[String: Any]] = []
        for path in CommandLine.arguments.dropFirst() {
            let root = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: path))) as! [String: Any]
            cases += root["cases"] as! [[String: Any]]
        }
        func decode(_ payload: [String: Any]) -> DeepfakeUpdate? {
            DeepfakeUpdate.decode(try! JSONSerialization.data(withJSONObject: payload))
        }
        for item in cases {
            let update = decode(item["payload"] as! [String: Any])!
            let value = update.assessment(at: now)
            precondition(value.state.rawValue == item["expected"] as! String, "state \(item["name"]!)")
            if let title = item["expected_title"] as? String { precondition(value.title == title, "title \(item["name"]!)") }
            if value.hasCurrentWarning {
                precondition(value.voice != .human && value.title != "Likely AI")
                precondition(!value.message.contains("appears human"))
            }
        }
        let base = cases.first { $0["name"] as? String == "high" }!["payload"] as! [String: Any]
        for key in ["schema", "type", "room", "callerIdentity", "streamID", "sequence", "model", "deepfake"] {
            var bad = base; bad[key] = nil
            precondition(decode(bad) == nil, "missing \(key)")
        }
        precondition(DeepfakeUpdate.decode(Data(repeating: 32, count: 16_385)) == nil)
        var monitor = DeepfakeMonitor()
        let update = decode(base)!
        precondition(monitor.receive(update, room: "wrong", callerIdentity: "sip-test", isAgent: true, at: now) == nil)
        precondition(monitor.receive(update, room: "call-test", callerIdentity: "sip-test", isAgent: false, at: now) == nil)
        precondition(monitor.receive(update, room: "call-test", callerIdentity: "sip-test", isAgent: true, at: now, monotonicTime: 100)?.voice == .ai)
        precondition(monitor.receive(update, room: "call-test", callerIdentity: "sip-test", isAgent: true, at: now) == nil)
        precondition(monitor.expire(at: now.addingTimeInterval(-300), connectedAt: now, monotonicTime: 112)?.state == .unavailable)
        var restart = base; restart["streamID"] = UUID().uuidString; restart["sequence"] = 1
        precondition(monitor.receive(decode(restart)!, room: "call-test", callerIdentity: "sip-test", isAgent: true, at: now)?.voice == .ai)
        var retired = base; retired["sequence"] = 999
        precondition(monitor.receive(decode(retired)!, room: "call-test", callerIdentity: "sip-test", isAgent: true, at: now) == nil)
        let id = UUID()
        var session = PhoneSessionState()
        _ = session.begin(PhoneCall(id: id, person: PhoneNumber.person("+13125550123"), direction: .incoming,
                                   createdAt: now.addingTimeInterval(-60), stage: .incoming))
        session.connected(id: id, at: now, monotonicTime: 100)
        session.finalizeInitialAssessment(id: id, at: now.addingTimeInterval(14.999), monotonicTime: 114.999)
        precondition(session.current?.deepfake?.state == .analyzing)
        session.finalizeInitialAssessment(id: id, at: now.addingTimeInterval(15), monotonicTime: 115)
        precondition(session.current?.deepfake?.state == .uncertain)
        let late = DeepfakeAssessment(state: .human, updatedAt: now.addingTimeInterval(16), windows: 3, score: 12)
        session.assessDeepfake(id: id, assessment: late, monotonicTime: 116)
        precondition(session.current?.deepfake?.scoreText == "Whole-call evidence: 12.0/100 · heuristic")
        session.recordVoiceDisplay(id: id, monotonicTime: 116.5)
        precondition(session.current?.analysisTiming.last?.elapsedSeconds == 16.5)
        session.assessDeepfake(id: id, assessment: DeepfakeAssessment(state: .waiting, updatedAt: now.addingTimeInterval(20)))
        precondition(session.current?.deepfake?.state == .human)
        session.assessDeepfake(id: id, assessment: DeepfakeAssessment(state: .unavailable, updatedAt: now.addingTimeInterval(25)))
        precondition(session.current?.lastDeepfakeResult == late)
        let record = session.finish(id: id, outcome: .completed, at: now.addingTimeInterval(26))!
        precondition(record.deepfake == late)
        let restored = try JSONDecoder().decode(PhoneCallRecord.self, from: JSONEncoder().encode(record))
        precondition(restored == record)
        var old = try JSONSerialization.jsonObject(with: JSONEncoder().encode(record)) as! [String: Any]
        old["analysisTiming"] = nil; old["deepfake"] = nil; old["transcript"] = nil
        let restoredOld = try JSONDecoder().decode(PhoneCallRecord.self, from: JSONSerialization.data(withJSONObject: old))
        precondition(restoredOld.deepfake == nil)
        print("Passed \(cases.count) production wire fixtures; malformed packets, scoped stream ordering/restart, monotonic timeout, connection deadline, late recovery, display timings and old/new history round-trip")
    }
}
