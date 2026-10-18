@preconcurrency import AVFoundation
import CryptoKit
import XCTest
@testable import Callshield

final class TranscriptPipelineTests: XCTestCase {
    private func fixture(_ name: String) throws -> URL {
        try XCTUnwrap(Bundle(for: Self.self).url(forResource: name, withExtension: "wav", subdirectory: "Fixtures"))
    }
    @MainActor
    private func waitFor(_ condition: () -> Bool, seconds: Int = 90) async throws {
        for _ in 0..<(seconds * 10) {
            if condition() { return }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        XCTFail("Timed out waiting for transcript pipeline")
    }
    #if DEBUG
    @MainActor
    func testRealSpeechFileToVoskToLocalJevAndSessionReset() async throws {
        let pipeline = TranscriptPipeline()
        let source = TranscriptTestSource(pipeline: pipeline)
        source.playFile(try fixture("scam"))
        try await waitFor { pipeline.state == .finished && !pipeline.scoring }
        XCTAssertNil(pipeline.error)
        XCTAssertTrue(pipeline.text.contains("verification"), pipeline.text)
        let score = try XCTUnwrap(pipeline.result)
        XCTAssertEqual(score.model, .behaviors)
        XCTAssertEqual(score.signals.count, 10)
        XCTAssertGreaterThan(score.latencyMS, 0)
        XCTAssertTrue(score.signals.allSatisfy { $0.value.isFinite && (0...1).contains($0.value) })
        print("CALLSHIELD_AUDIO_JEV: \(pipeline.text) | \(score.latencyMS) ms")
        pipeline.select(.rules)
        source.playFile(try fixture("dentist"))
        try await waitFor { pipeline.state == .finished && !pipeline.scoring }
        XCTAssertNil(pipeline.error)
        XCTAssertFalse(pipeline.text.contains("verification"), pipeline.text)
        XCTAssertEqual(pipeline.result?.summary, "No strong indicators")
    }
    @MainActor
    func testOldInferenceCannotPublishAfterModelChangeOrNewSession() async throws {
        let pipeline = TranscriptPipeline()
        pipeline.testText("Tell me your password and give me your verification code now.")
        pipeline.select(.rules)
        pipeline.testText("Your dentist is confirming your appointment tomorrow.")
        try await waitFor { !pipeline.scoring }
        XCTAssertEqual(pipeline.result?.model, .rules)
        XCTAssertEqual(pipeline.result?.text, pipeline.text)
        XCTAssertEqual(pipeline.result?.summary, "No strong indicators")
        pipeline.cancel()
        XCTAssertNil(pipeline.result)
        XCTAssertTrue(pipeline.text.isEmpty)
    }
    @MainActor
    func testCallerCheckpointIsAvailableInCallshield() async throws {
        let pipeline = TranscriptPipeline()
        pipeline.select(.caller)
        pipeline.testText("Give me your bank verification code right now.")
        try await waitFor { !pipeline.scoring }
        XCTAssertNil(pipeline.error)
        XCTAssertEqual(pipeline.result?.signals.count, 1)
        XCTAssertEqual(pipeline.result?.model, .caller)
    }
    #endif

    func testMuLawKnownValuesAndFormat() throws {
        XCTAssertEqual(TwilioMediaDecoder.expandMuLaw(0xff), 0)
        XCTAssertEqual(TwilioMediaDecoder.expandMuLaw(0x7f), 0)
        XCTAssertEqual(TwilioMediaDecoder.expandMuLaw(0x00), -32124)
        XCTAssertEqual(TwilioMediaDecoder.expandMuLaw(0x80), 32124)
        let buffer = try TwilioMediaDecoder.muLawPCM(Data([0xff, 0x00, 0x80]))
        XCTAssertEqual(buffer.format.sampleRate, 8000)
        XCTAssertEqual(buffer.format.channelCount, 1)
        let converted = try PCMConverter(inputFormat: buffer.format).convert(buffer)
        XCTAssertEqual(converted.format.sampleRate, 16000)
    }
    private func json(_ value: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: value) }
    private func start(_ sid: String = "CA_test") throws -> Data {
        try json(["event": "start", "streamSid": "MZ_test", "start": ["streamSid": "MZ_test", "callSid": sid,
                  "tracks": ["inbound", "outbound"], "mediaFormat": ["encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1]]])
    }
    private func media(_ track: String = "inbound", chunk: Int = 1, stream: String = "MZ_test", bytes: Data = Data([0xff])) throws -> Data {
        try json(["event": "media", "streamSid": stream, "media": ["track": track, "chunk": String(chunk), "payload": bytes.base64EncodedString()]])
    }
    func testStreamIdentityCallerTrackDuplicatesGapsAndInvalidPayload() throws {
        var decoder = TwilioMediaDecoder(callerTrack: "inbound", expectedCallSID: "CA_test")
        XCTAssertThrowsError(try decoder.decode(media()))
        XCTAssertThrowsError(try decoder.decode(start("CA_wrong")))
        _ = try decoder.decode(start())
        if case .none = try decoder.decode(media("outbound")) {} else { XCTFail("Local speaker must be ignored") }
        if case .audio = try decoder.decode(media()) {} else { XCTFail("Expected caller audio") }
        if case .none = try decoder.decode(media()) {} else { XCTFail("Duplicate must be ignored") }
        XCTAssertThrowsError(try decoder.decode(media(chunk: 3)))
        XCTAssertThrowsError(try decoder.decode(media(chunk: 2, stream: "MZ_wrong")))
        XCTAssertThrowsError(try decoder.decode(media(chunk: 2, bytes: Data())))
    }
    private func telephoneSpeech() throws -> Data {
        let file = try AVAudioFile(forReading: fixture("scam"))
        let format = try XCTUnwrap(AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 8000, channels: 1, interleaved: true))
        let converter = try XCTUnwrap(AVAudioConverter(from: file.processingFormat, to: format))
        let input = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length)))
        try file.read(into: input)
        let output = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(Double(file.length) / 6 + 64)))
        var supplied = false, conversionError: NSError?
        let status = converter.convert(to: output, error: &conversionError) { _, state in
            if supplied { state.pointee = .endOfStream; return nil }
            supplied = true; state.pointee = .haveData; return input
        }
        XCTAssertNotEqual(status, .error); XCTAssertNil(conversionError)
        let samples = try XCTUnwrap(output.int16ChannelData?[0])
        // Encode independently by selecting the closest of G.711's 256 decoded values.
        let table = (0...255).map { Int(TwilioMediaDecoder.expandMuLaw(UInt8($0))) }
        let bytes = Data((0..<Int(output.frameLength)).map { i in
            UInt8(table.indices.min { abs(table[$0] - Int(samples[i])) < abs(table[$1] - Int(samples[i])) }!)
        })
        return bytes
    }
    @MainActor
    func testActualEightKHzMuLawSpeechThroughTwilioDecoderAndJev() async throws {
        let bytes = try telephoneSpeech()
        var decoder = TwilioMediaDecoder(callerTrack: "inbound", expectedCallSID: "CA_test")
        _ = try decoder.decode(start())
        let pipeline = TranscriptPipeline(), id = UUID()
        pipeline.begin(callID: id)
        var chunk = 0
        for offset in stride(from: 0, to: bytes.count, by: 160) {
            chunk += 1
            if case .audio(let buffer) = try decoder.decode(media(chunk: chunk, bytes: bytes.subdata(in: offset..<min(offset + 160, bytes.count)))) {
                pipeline.accept(buffer, callID: id)
            }
            if chunk % 16 == 0 { await pipeline.drainAudio() }
        }
        pipeline.finish(callID: id)
        try await waitFor { pipeline.state == .finished && !pipeline.scoring }
        XCTAssertNil(pipeline.error)
        // Telephone bandwidth can change individual words. Assert actual speech
        // reaches the classifier, without pretending this is an ASR accuracy test.
        XCTAssertTrue(pipeline.text.contains("code"), pipeline.text)
        XCTAssertTrue(pipeline.text.contains("stay on the line"), pipeline.text)
        XCTAssertEqual(pipeline.result?.signals.count, 10)
        print("CALLSHIELD_TWILIO_MULAW_JEV: \(pipeline.text)")
    }
    @MainActor
    func testAuthenticatedWebSocketRelayToLocalJev() async throws {
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8765/sessions")!)
        request.httpMethod = "POST"
        request.setValue("Bearer test-admin", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try json(["call_sid": "CA_test", "caller_track": "inbound"])
        let data: Data
        do { (data, _) = try await URLSession.shared.data(for: request) }
        catch { throw XCTSkip("Start backend/transcript-relay with the documented local test credentials for this integration test.") }
        let sub = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let sid = try XCTUnwrap(sub["session_id"] as? String)
        let token = try XCTUnwrap(sub["bearer_token"] as? String)
        let pipeline = TranscriptPipeline(), id = UUID(), stream = CallerAudioStream()
        pipeline.begin(callID: id)
        try stream.connect(.init(url: URL(string: "ws://127.0.0.1:8765/audio/" + sid)!, bearerToken: token,
                                 callerTrack: "inbound", callSID: "CA_test"), callID: id, pipeline: pipeline)
        defer { stream.disconnect(); pipeline.cancel() }
        let signature = Data(HMAC<Insecure.SHA1>.authenticationCode(
            for: Data(("https://relay.example/twilio/" + sid).utf8),
            using: SymmetricKey(data: Data("test-twilio-token".utf8)))).base64EncodedString()
        var upgrade = URLRequest(url: URL(string: "ws://127.0.0.1:8765/twilio/" + sid)!)
        upgrade.setValue(signature, forHTTPHeaderField: "X-Twilio-Signature")
        let twilio = URLSession.shared.webSocketTask(with: upgrade); twilio.resume()
        defer { twilio.cancel(with: .goingAway, reason: nil) }
        try await twilio.send(.string(String(decoding: start(), as: UTF8.self)))
        let bytes = try telephoneSpeech()
        var chunk = 0
        for offset in stride(from: 0, to: bytes.count, by: 160) {
            chunk += 1
            let frame = try media(chunk: chunk, bytes: bytes.subdata(in: offset..<min(offset + 160, bytes.count)))
            try await twilio.send(.string(String(decoding: frame, as: UTF8.self)))
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        try await twilio.send(.string(String(decoding: json(["event": "stop", "streamSid": "MZ_test"]), as: UTF8.self)))
        try await waitFor { pipeline.state == .finished && !pipeline.scoring }
        XCTAssertNil(pipeline.error)
        XCTAssertTrue(pipeline.text.contains("code"), pipeline.text)
        XCTAssertEqual(pipeline.result?.signals.count, 10)
        print("CALLSHIELD_WEBSOCKET_AUDIO_JEV: \(pipeline.text)")
    }
    @MainActor
    func testStaleAudioAndErrorsCannotAffectAnotherCall() async throws {
        let pipeline = TranscriptPipeline(), oldID = UUID(), newID = UUID()
        pipeline.begin(callID: oldID); pipeline.begin(callID: newID)
        pipeline.reportFailure(PipelineError.disconnected, callID: oldID)
        pipeline.finish(callID: oldID)
        await pipeline.drainAudio()
        try await waitFor { pipeline.state == .listening }
        XCTAssertEqual(pipeline.callID, newID); XCTAssertNil(pipeline.error)
        pipeline.cancel()
    }
}
