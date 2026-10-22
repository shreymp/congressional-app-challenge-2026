import AVFoundation
import XCTest
@testable import ScamTranscript

final class VoskIntegrationTests: XCTestCase {
    func testActualVoskAudioToRuleClassificationAndSessionReset() throws {
        let recognizer = try VoskRecognizer()
        for (fixture, expected) in [("scam", ScamClassifier.Level.high), ("dentist", .clear), ("bank", .clear)] {
            let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: fixture, withExtension: "wav", subdirectory: "Fixtures"))
            let file = try AVAudioFile(forReading: url)
            XCTAssertGreaterThan(file.length, 48_000, "Fixture must contain actual speech")
            XCTAssertEqual(file.processingFormat.sampleRate, 48_000)
            let converter = try PCMConverter(inputFormat: file.processingFormat)
            try recognizer.begin()
            var window = TranscriptWindow()
            var sawPartial = false
            let start = Date()
            while file.framePosition < file.length {
                let input = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: 2048))
                try file.read(into: input)
                let pcm = try converter.convert(input)
                if pcm.frameLength == 0 { continue }
                XCTAssertEqual(pcm.format.channelCount, 1)
                let result = try recognizer.accept(pcm)
                if result.isFinal { window.commit(result.text) }
                else { window.updatePartial(result.text); sawPartial = sawPartial || !result.text.isEmpty }
            }
            window.commit(try recognizer.finish())
            XCTAssertFalse(window.finalized.isEmpty, fixture)
            XCTAssertTrue(sawPartial, "Expected streaming partials for \(fixture)")
            let assessment = ScamClassifier().assess(window.text)
            print("VOSK_FIXTURE \(fixture): \(window.text) | \(assessment.level.rawValue) | elapsed \(Date().timeIntervalSince(start))s")
            XCTAssertEqual(assessment.level, expected, "\(fixture): \(window.text)")
        }
    }
    func testInvalidAudioFormatIsRejected() throws {
        let recognizer = try VoskRecognizer()
        try recognizer.begin()
        let format = try XCTUnwrap(AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 2))
        let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 16))
        buffer.frameLength = 16
        XCTAssertThrowsError(try recognizer.accept(buffer))
    }
}
