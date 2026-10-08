import XCTest
@testable import ScamTranscript

final class JevCallDecisionMakerTests: XCTestCase {
    func testBothCheckpointsMatchPythonIncludingLongTranscript() throws {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "jev-call-golden", withExtension: "json", subdirectory: "Fixtures"))
        let examples = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [[String: Any]])
        for version in [1, 2] {
            let model = try JevCallDecisionMaker(version: version)
            for example in examples where example["version"] as? Int == version {
                let text = try XCTUnwrap(example["text"] as? String)
                let actual = try model.score(text)
                XCTAssertEqual(actual.score, try XCTUnwrap(example["score"] as? Double), accuracy: 0.0001)
                XCTAssertEqual(actual.wasTrimmed, text.count > 1000)
                print("NATIVE_CALL_V\(version): \(actual.score), \(actual.latencyMS) ms")
            }
        }
    }

    @MainActor
    func testTypedTranscriptUsesSelectedCheckpointAndSuppressesOldMode() async throws {
        let controller = RecordingController()
        controller.selectDecisionMaker(.callV1)
        controller.testTranscript("Caller: Give me your bank verification code right now.")
        controller.selectDecisionMaker(.callV2)
        controller.testTranscript("Caller: Your dentist is confirming your appointment tomorrow.")
        for _ in 0..<600 {
            if !controller.jevBusy { break }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        XCTAssertFalse(controller.jevBusy)
        XCTAssertFalse(controller.logs.contains { $0.text.contains("Trained Jev v1: experimental scam score") })
        XCTAssertTrue(controller.logs.contains { $0.text.contains("Trained Jev v2 (caller): experimental scam score") })
        XCTAssertTrue(controller.logs.contains { $0.text.contains("Scored: Caller: Your dentist") })
    }
}
