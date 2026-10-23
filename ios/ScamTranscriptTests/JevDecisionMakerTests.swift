import XCTest
@testable import ScamTranscript

final class JevDecisionMakerTests: XCTestCase {
    private func golden() throws -> [String: Any] {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "jev-golden", withExtension: "json", subdirectory: "Fixtures"))
        return try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
    }

    func testTokenizerMatchesPythonForPromptsUnicodeAndSpecialTokens() throws {
        let directory = try XCTUnwrap(Bundle.main.url(forResource: "Jev", withExtension: nil))
        let tokenizer = try JevTokenizer(url: directory.appendingPathComponent("tokenizer.json"))
        let vectors = try XCTUnwrap(try golden()["vectors"] as? [[String: Any]])
        for vector in vectors {
            let text = try XCTUnwrap(vector["text"] as? String)
            let ids = try XCTUnwrap(vector["ids"] as? [Int64])
            XCTAssertEqual(try tokenizer.encode(text), ids, text)
        }
    }

    func testNativeJevMatchesExistingPythonAdapter() throws {
        let model = try JevDecisionMaker()
        let assessments = try XCTUnwrap(try golden()["assessments"] as? [[String: Any]])
        for example in assessments {
            let text = try XCTUnwrap(example["text"] as? String)
            let expected = try XCTUnwrap(example["result"] as? [String: Any])
            let signals = try XCTUnwrap(expected["signals"] as? [String: [String: Any]])
            let actual = try model.score(text)
            XCTAssertEqual(actual.signals.count, 10)
            for signal in actual.signals {
                let baseline = try XCTUnwrap(signals[signal.id])
                XCTAssertEqual(signal.probability, try XCTUnwrap(baseline["probability"] as? Double), accuracy: 0.0001, signal.label)
                XCTAssertEqual(signal.insufficientEvidence, try XCTUnwrap(baseline["insufficient_evidence_probability"] as? Double), accuracy: 0.0001, signal.label)
            }
            print("NATIVE_JEV \(text): strongest \(actual.strongest!.label) \(actual.strongest!.probability), \(actual.latencyMS) ms")
        }
    }

    @MainActor
    func testSwitchScoresSameTranscriptAndPrintsJevResult() async throws {
        let controller = RecordingController()
        controller.processTranscript("Tell me your verification code right now. Do not tell anyone.", isFinal: true)
        controller.switchDecisionMaker()
        XCTAssertEqual(controller.decisionMaker, .jev)
        for _ in 0..<300 {
            if !controller.jevBusy { break }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        XCTAssertFalse(controller.jevBusy)
        XCTAssertTrue(controller.logs.contains { $0.text.contains("Jev result: strongest behavior") })
        controller.printLastScore()
        XCTAssertTrue(controller.logs.contains { $0.text.contains("Last Jev score:") })
        controller.switchDecisionMaker()
        XCTAssertEqual(controller.decisionMaker, .rules)
        XCTAssertTrue(controller.logs.last?.text.contains("Last score: 7 | High concern") == true)
    }

    @MainActor
    func testSwitchBackIgnoresInFlightJevResult() async throws {
        let controller = RecordingController()
        controller.processTranscript("Give me your password right now.", isFinal: true)
        controller.switchDecisionMaker()
        controller.switchDecisionMaker()
        for _ in 0..<300 {
            if !controller.jevBusy { break }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        XCTAssertFalse(controller.jevBusy)
        XCTAssertEqual(controller.decisionMaker, .rules)
        XCTAssertFalse(controller.logs.contains { $0.text.contains("Jev result:") })
    }
}
