import Foundation

enum JevError: LocalizedError {
    case missingModel, invalidTokenizer, invalidModel, emptyTranscript
    var errorDescription: String? {
        switch self {
        case .missingModel: return "Jev assets missing. Run python3 ios/scripts/setup_jev.py and rebuild."
        case .invalidTokenizer: return "Jev tokenizer format is unsupported or corrupt."
        case .invalidModel: return "Jev returned invalid model scores."
        case .emptyTranscript: return "Jev is waiting for speech."
        }
    }
}

struct JevSignalDefinition: Codable {
    let id: String
    let label: String
    let proposition: String
}

struct JevAssessment {
    struct Signal {
        let id: String
        let label: String
        /// Same conditional score as the existing Python adapter, not a scam probability.
        let probability: Double
        let insufficientEvidence: Double
    }
    let transcript: String
    let signals: [Signal]
    let latencyMS: Double
    let wasTrimmed: Bool
    var strongest: Signal? { signals.max { $0.probability < $1.probability } }
}

/// Serial-queue-only port of backend/jev-prototype/jev_scam_signals.py.
/// Preserves the prototype's prompt and first-three-logit semantics; accuracy
/// and candidate-slot interpretation remain unvalidated for scam detection.
final class JevDecisionMaker {
    private let runtime: JevRuntime
    let tokenizer: JevTokenizer
    let definitions: [JevSignalDefinition]
    private let temperature: Double

    init(bundle: Bundle = .main) throws {
        guard let directory = bundle.url(forResource: "Jev", withExtension: nil),
              let signalURL = bundle.url(forResource: "JevSignals", withExtension: "json"),
              FileManager.default.fileExists(atPath: directory.appendingPathComponent("model.onnx").path) else {
            throw JevError.missingModel
        }
        tokenizer = try JevTokenizer(url: directory.appendingPathComponent("tokenizer.json"))
        definitions = try JSONDecoder().decode([JevSignalDefinition].self, from: Data(contentsOf: signalURL))
        guard definitions.count == 10,
              let calibration = try JSONSerialization.jsonObject(with: Data(contentsOf: directory.appendingPathComponent("calibrator.json"))) as? [String: Any],
              let baseTemperature = calibration["temperature"] as? Double else { throw JevError.invalidModel }
        temperature = (calibration["per_k"] as? [String: Double])?["3"] ?? baseTemperature
        guard temperature.isFinite, temperature > 0 else { throw JevError.invalidModel }
        runtime = try JevRuntime(modelPath: directory.appendingPathComponent("model.onnx").path)
    }

    static func render(proposition: String, transcript: String) -> String {
        "<<LABEL>>true: \(proposition)<<LABEL>>false: not \(proposition)<<LABEL>>insufficient evidence<<SEP>>Context:\n\(transcript)\n\nEvaluate proposition: \(proposition)"
    }

    func score(_ transcript: String) throws -> JevAssessment {
        var text = transcript.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        guard !text.isEmpty else { throw JevError.emptyTranscript }
        var tokens = try tokenizer.encode(text, specialTokens: false)
        var trimmed = tokens.count > 350
        if trimmed { text = try tokenizer.decode(Array(tokens.suffix(350))) }
        var prompts = try definitions.map { try tokenizer.encode(Self.render(proposition: $0.proposition, transcript: text)) }
        while (prompts.map(\.count).max() ?? 0) > 512 {
            tokens = try tokenizer.encode(text, specialTokens: false)
            guard tokens.count > 16 else { throw JevError.invalidModel }
            text = try tokenizer.decode(Array(tokens.suffix(tokens.count - 16)))
            trimmed = true
            prompts = try definitions.map { try tokenizer.encode(Self.render(proposition: $0.proposition, transcript: text)) }
        }
        let length = prompts.map(\.count).max() ?? 0
        var ids: [NSNumber] = []
        var masks: [NSNumber] = []
        for prompt in prompts {
            ids += prompt.map { NSNumber(value: $0) }
            ids += Array(repeating: NSNumber(value: tokenizer.paddingID), count: length - prompt.count)
            masks += Array(repeating: NSNumber(value: 1), count: prompt.count)
            masks += Array(repeating: NSNumber(value: 0), count: length - prompt.count)
        }
        let start = Date()
        let logits = try runtime.runInputIDs(ids, attentionMask: masks, batchSize: 10, sequenceLength: length)
        let latency = Date().timeIntervalSince(start) * 1000
        guard logits.count == 250 else { throw JevError.invalidModel }
        let signals = try definitions.enumerated().map { index, definition -> JevAssessment.Signal in
            let values = (0..<3).map { logits[index * 25 + $0].doubleValue / temperature }
            guard values.allSatisfy(\.isFinite), let maxValue = values.max() else { throw JevError.invalidModel }
            let expValues = values.map { exp($0 - maxValue) }
            let total = expValues.reduce(0, +)
            let yes = expValues[0] / total
            let no = expValues[1] / total
            return JevAssessment.Signal(id: definition.id, label: definition.label,
                                        probability: yes / (yes + no), insufficientEvidence: expValues[2] / total)
        }
        return JevAssessment(transcript: text, signals: signals, latencyMS: latency, wasTrimmed: trimmed)
    }
}

struct JevCallAssessment {
    let transcript: String
    let score: Double
    let latencyMS: Double
    let wasTrimmed: Bool
}

/// Overall-call classifier; these checkpoints are not behavior classifiers.
final class JevCallDecisionMaker {
    static let proposition = "The caller is attempting to scam or defraud the other person."
    private let runtime: JevRuntime
    private let tokenizer: JevTokenizer
    private let temperature: Double

    init(version: Int, bundle: Bundle = .main) throws {
        guard [1, 2].contains(version),
              let directory = bundle.url(forResource: "JevCallV\(version)", withExtension: nil) else {
            throw JevError.missingModel
        }
        tokenizer = try JevTokenizer(url: directory.appendingPathComponent("tokenizer.json"))
        guard let calibration = try JSONSerialization.jsonObject(with: Data(contentsOf: directory.appendingPathComponent("calibration.json"))) as? [String: Double],
              let value = calibration["temperature"], value.isFinite, value > 0 else { throw JevError.invalidModel }
        temperature = value
        runtime = try JevRuntime(modelPath: directory.appendingPathComponent("model.onnx").path)
    }

    func score(_ transcript: String) throws -> JevCallAssessment {
        var text = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { throw JevError.emptyTranscript }
        let tokens = try tokenizer.encode(text, specialTokens: false)
        let trimmed = tokens.count > 300
        if trimmed { text = try tokenizer.decode(Array(tokens.suffix(300))) }
        let ids = try tokenizer.encode(JevDecisionMaker.render(proposition: Self.proposition, transcript: text))
        guard ids.count <= 512 else { throw JevError.invalidModel }
        let start = Date()
        let logits = try runtime.runInputIDs(ids.map { NSNumber(value: $0) },
            attentionMask: Array(repeating: NSNumber(value: 1), count: ids.count), batchSize: 1, sequenceLength: ids.count)
        guard logits.count == 25 else { throw JevError.invalidModel }
        let margin = (logits[0].doubleValue - logits[1].doubleValue) / temperature
        guard margin.isFinite else { throw JevError.invalidModel }
        let value = margin >= 0 ? 1 / (1 + exp(-margin)) : exp(margin) / (1 + exp(margin))
        return JevCallAssessment(transcript: text, score: value,
            latencyMS: Date().timeIntervalSince(start) * 1000, wasTrimmed: trimmed)
    }
}
