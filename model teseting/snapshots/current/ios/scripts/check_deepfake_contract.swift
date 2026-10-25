// Foundation-only smoke checks, runnable with the Swift CLI without Xcode/iOS SDK.
import Foundation

@main
struct DeepfakeContractCheck {
    static func main() throws {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let url = URL(fileURLWithPath: CommandLine.arguments[1])
        let root = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        let cases = root["cases"] as! [[String: Any]]
        for item in cases {
            let data = try JSONSerialization.data(withJSONObject: item["payload"]!)
            guard let update = DeepfakeUpdate.decode(data) else { fatalError("Cannot decode \(item["name"]!)") }
            precondition(update.assessment(at: now).state.rawValue == item["expected"] as! String)
        }
        var session = PhoneSessionState()
        let id = UUID()
        _ = session.begin(PhoneCall(id: id, person: PhoneNumber.person("+13125550123"),
                                   direction: .incoming, createdAt: now.addingTimeInterval(-40), stage: .incoming))
        session.connected(id: id, at: now)
        precondition(session.current?.deepfake?.title == "Analyzing")
        session.finalizeInitialAssessment(id: id, at: now.addingTimeInterval(14.999))
        precondition(session.current?.deepfake?.state == .analyzing)
        session.finalizeInitialAssessment(id: id, at: now.addingTimeInterval(15))
        precondition(session.current?.deepfake?.title == "Inconclusive")
        precondition(session.current?.deepfake?.score == nil)
        session.assessDeepfake(id: id, assessment: DeepfakeAssessment(state: .human, updatedAt: now.addingTimeInterval(16), windows: 2, score: 12))
        precondition(session.current?.deepfake?.scoreText == "AI score: 12/100")
        session.assessDeepfake(id: id, assessment: DeepfakeAssessment(state: .waiting, updatedAt: now.addingTimeInterval(20)))
        precondition(session.current?.deepfake?.state == .human)
        let record = session.finish(id: id, outcome: .completed, at: now.addingTimeInterval(25))!
        let restored = try JSONDecoder().decode(PhoneCallRecord.self, from: JSONEncoder().encode(record))
        precondition(restored == record)
        print("Passed \(cases.count) wire fixtures, 15-second deadline, late recovery, pause retention and history round-trip")
    }
}
