import Foundation
import AVFoundation

enum TranscriptionError: LocalizedError {
    case missingModel, modelFailed, recognizerFailed, invalidAudio, conversionFailed, decoderFailed
    var errorDescription: String? {
        switch self {
        case .missingModel: return "Vosk model missing. Run ios/scripts/setup_vosk.py, then rebuild."
        case .modelFailed: return "Vosk could not load the English model."
        case .recognizerFailed: return "Vosk could not create a recognizer."
        case .invalidAudio: return "The microphone has no usable audio input."
        case .conversionFailed: return "Audio conversion to 16 kHz mono PCM failed."
        case .decoderFailed: return "Vosk could not decode this audio."
        }
    }
}

/// Access only on the recognition worker queue; Vosk pointers never cross queues.
final class VoskRecognizer {
    private let model: OpaquePointer
    private var recognizer: OpaquePointer?
    init(bundle: Bundle = .main) throws {
        guard let path = bundle.url(forResource: "vosk-model-small-en-us-0.15", withExtension: nil) else {
            throw TranscriptionError.missingModel
        }
        vosk_set_log_level(-1)
        guard let model = vosk_model_new(path.path) else { throw TranscriptionError.modelFailed }
        self.model = model
    }
    deinit {
        if let recognizer { vosk_recognizer_free(recognizer) }
        vosk_model_free(model)
    }
    func begin() throws {
        if let recognizer { vosk_recognizer_free(recognizer) }
        recognizer = vosk_recognizer_new(model, 16_000)
        guard recognizer != nil else { throw TranscriptionError.recognizerFailed }
    }
    func accept(_ buffer: AVAudioPCMBuffer) throws -> (text: String, isFinal: Bool) {
        guard let recognizer, let samples = buffer.int16ChannelData?[0],
              buffer.format.sampleRate == 16_000, buffer.format.channelCount == 1 else {
            throw TranscriptionError.invalidAudio
        }
        let bytes = Int(buffer.frameLength) * MemoryLayout<Int16>.size
        let status = samples.withMemoryRebound(to: CChar.self, capacity: bytes) {
            vosk_recognizer_accept_waveform(recognizer, $0, Int32(bytes))
        }
        guard status >= 0 else { throw TranscriptionError.decoderFailed }
        let isFinal = status == 1
        let pointer = isFinal ? vosk_recognizer_result(recognizer) : vosk_recognizer_partial_result(recognizer)
        return (try parse(pointer, key: isFinal ? "text" : "partial"), isFinal)
    }
    func finish() throws -> String {
        guard let recognizer else { return "" }
        let text = try parse(vosk_recognizer_final_result(recognizer), key: "text")
        vosk_recognizer_free(recognizer)
        self.recognizer = nil
        return text
    }
    private func parse(_ pointer: UnsafePointer<CChar>?, key: String) throws -> String {
        guard let pointer, let data = String(cString: pointer).data(using: .utf8),
              let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let value = json[key] as? String else { throw TranscriptionError.decoderFailed }
        return value
    }
}

/// Persistent resampler: accepts the hardware format, emits exactly the PCM
/// format used by Vosk. Never change the recognizer rate without resampling.
final class PCMConverter {
    let outputFormat: AVAudioFormat
    private let converter: AVAudioConverter
    init(inputFormat: AVAudioFormat) throws {
        guard inputFormat.sampleRate > 0, inputFormat.channelCount > 0,
              let output = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16_000,
                                         channels: 1, interleaved: true),
              let converter = AVAudioConverter(from: inputFormat, to: output) else {
            throw TranscriptionError.invalidAudio
        }
        outputFormat = output
        self.converter = converter
    }
    func convert(_ input: AVAudioPCMBuffer) throws -> AVAudioPCMBuffer {
        let capacity = AVAudioFrameCount(ceil(Double(input.frameLength) * 16_000 / input.format.sampleRate)) + 64
        guard let output = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else {
            throw TranscriptionError.conversionFailed
        }
        var supplied = false
        var error: NSError?
        let status = converter.convert(to: output, error: &error) { _, state in
            if supplied { state.pointee = .noDataNow; return nil }
            supplied = true
            state.pointee = .haveData
            return input
        }
        if status == .error || error != nil { throw error ?? TranscriptionError.conversionFailed as NSError }
        return output
    }
}
