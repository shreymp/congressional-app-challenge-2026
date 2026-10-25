// Evaluation harness, Foundation-only; no LiveKit, CallKit, network, or audio inference.
import Foundation

@main
struct WireFixtureCheck {
    static func main() throws {
        let root = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))) as! [String: Any]
        let cases = root["cases"] as! [[String: Any]]
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        for item in cases {
            let data = try JSONSerialization.data(withJSONObject: item["payload"]!)
            guard let update = DeepfakeUpdate.decode(data) else { fatalError("Cannot decode \(item["name"]!)") }
            precondition(update.assessment(at: now).state.rawValue == item["expected"] as! String)
        }
        precondition(DeepfakeUpdate.decode(Data("not json".utf8)) == nil)
        precondition(DeepfakeUpdate.decode(Data(repeating: 32, count: 16_385)) == nil)
        print("Passed \(cases.count) Python/Swift wire fixtures plus malformed/oversize rejection")
    }
}
