@preconcurrency import AVFoundation
import Combine
import Foundation

struct TranscriptResult: Equatable {
    struct Signal: Identifiable, Equatable {
        let id: String
        let label: String
        let value: Double
        let insufficientEvidence: Double?
    }
    let text: String
    let model: TranscriptPipeline.Model
    let summary: String
    let signals: [Signal]
    let latencyMS: Double
    let wasTrimmed: Bool
}

private final class TranscriptASRWorker: @unchecked Sendable {
    let queue = DispatchQueue(label: "org.callshield.transcript.asr", qos: .userInitiated)
    var recognizer: VoskRecognizer?
    var converter: PCMConverter?
    var format: AVAudioFormat?
    private let lock = NSLock()
    private var pending = 0
    func reserve() -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard pending < 128 else { return false }
        pending += 1; return true
    }
    func release() { lock.lock(); pending -= 1; lock.unlock() }
}

private final class TranscriptScoreWorker: @unchecked Sendable {
    let queue = DispatchQueue(label: "org.callshield.transcript.jev", qos: .utility)
    var behaviors: JevDecisionMaker?
    var caller: JevCallDecisionMaker?
    func score(_ text: String, model: TranscriptPipeline.Model) throws -> TranscriptResult {
        switch model {
        case .rules:
            let score = ScamClassifier().assess(text)
            return TranscriptResult(text: text, model: model, summary: score.level.rawValue,
                signals: score.signals.map { .init(id: $0.id, label: $0.label, value: Double($0.weight), insufficientEvidence: nil) },
                latencyMS: 0, wasTrimmed: false)
        case .behaviors:
            caller = nil
            if behaviors == nil { behaviors = try JevDecisionMaker() }
            let score = try behaviors!.score(text)
            return TranscriptResult(text: text, model: model, summary: "Experimental behavior estimates",
                signals: score.signals.map { .init(id: $0.id, label: $0.label, value: $0.probability, insufficientEvidence: $0.insufficientEvidence) },
                latencyMS: score.latencyMS, wasTrimmed: score.wasTrimmed)
        case .caller:
            behaviors = nil
            if caller == nil { caller = try JevCallDecisionMaker(version: 2) }
            let score = try caller!.score(text)
            return TranscriptResult(text: text, model: model, summary: "Experimental caller score",
                signals: [.init(id: "caller", label: "Scam-like caller text", value: score.score, insufficientEvidence: nil)],
                latencyMS: score.latencyMS, wasTrimmed: score.wasTrimmed)
        }
    }
}

/// One caller-only session. Vosk and Jev each have their own serial queue.
/// Media providers pass owned PCM buffers; this class never taps Phone.app audio.
@MainActor
final class TranscriptPipeline: ObservableObject {
    enum Model: String, CaseIterable { case behaviors = "Jev behaviors", caller = "Jev v2 caller", rules = "Rules" }
    enum State: String { case idle = "Ready", preparing = "Loading speech model…", listening = "Listening", finishing = "Finishing transcript…", finished = "Finished", failed = "Analysis unavailable" }
    @Published private(set) var state: State = .idle
    @Published private(set) var text = ""
    @Published private(set) var result: TranscriptResult?
    @Published private(set) var error: String?
    @Published private(set) var scoring = false
    @Published private(set) var isPaused = false
    @Published private(set) var model: Model = .behaviors
    private(set) var callID: UUID?
    private let asr = TranscriptASRWorker()
    private let scorer = TranscriptScoreWorker()
    private var epoch = UUID()
    private var scoreEpoch = UUID()
    private var window = TranscriptWindow()
    private var lastScoreTime = Date.distantPast
    private var pendingScore: String?
    private var lastRequested = ""
    private var lastPublishTime = Date.distantPast
    var onChange: (() -> Void)?

    init(model: Model = .behaviors) { self.model = model }

    func begin(callID: UUID) {
        cancel()
        self.callID = callID
        state = .preparing
        let generation = epoch
        asr.queue.async { [weak self, asr] in
            do {
                if asr.recognizer == nil { asr.recognizer = try VoskRecognizer() }
                try asr.recognizer!.begin()
                asr.converter = nil; asr.format = nil
                DispatchQueue.main.async {
                    guard let self, self.epoch == generation else { return }
                    self.state = .listening; self.onChange?()
                }
            } catch { DispatchQueue.main.async { self?.fail(error, generation: generation) } }
        }
        onChange?()
    }

    func select(_ model: Model) {
        self.model = model; scoreEpoch = UUID(); result = nil; pendingScore = nil; lastRequested = ""
        lastScoreTime = .distantPast
        requestScore(force: true); onChange?()
    }

    /// Called on the main actor after copying the provider's buffer out of its realtime callback.
    func accept(_ buffer: AVAudioPCMBuffer, callID: UUID) {
        guard self.callID == callID, !isPaused, state == .preparing || state == .listening else { return }
        let generation = epoch
        guard asr.reserve() else { fail(PipelineError.overloaded, generation: generation); return }
        asr.queue.async { [weak self, asr] in
            defer { asr.release() }
            do {
                if asr.format != buffer.format {
                    asr.converter = try PCMConverter(inputFormat: buffer.format); asr.format = buffer.format
                }
                let pcm = try asr.converter!.convert(buffer)
                guard pcm.frameLength > 0 else { return }
                guard let recognizer = asr.recognizer else { throw TranscriptionError.recognizerFailed }
                let recognized = try recognizer.accept(pcm)
                DispatchQueue.main.async { self?.receive(recognized.text, final: recognized.isFinal, generation: generation) }
            } catch { DispatchQueue.main.async { self?.fail(error, generation: generation) } }
        }
    }

    func finish(callID: UUID) {
        guard self.callID == callID, state == .preparing || state == .listening else { return }
        state = .finishing
        let generation = epoch
        asr.queue.async { [weak self, asr] in
            do {
                let final = try asr.recognizer?.finish() ?? ""
                asr.converter = nil; asr.format = nil
                DispatchQueue.main.async {
                    guard let self, self.epoch == generation else { return }
                    self.receive(final, final: true, generation: generation)
                    self.state = .finished; self.onChange?()
                }
            } catch { DispatchQueue.main.async { self?.fail(error, generation: generation) } }
        }
        onChange?()
    }

    func drainAudio() async {
        await withCheckedContinuation { continuation in asr.queue.async { continuation.resume() } }
    }

    func cancel() {
        epoch = UUID(); scoreEpoch = UUID(); callID = nil; pendingScore = nil
        window = TranscriptWindow(); text = ""; result = nil; error = nil; state = .idle
        isPaused = false
        lastRequested = ""; lastScoreTime = .distantPast; lastPublishTime = .distantPast
        // Existing inference completes on its worker, but cannot publish into a new session.
        asr.queue.async { [asr] in _ = try? asr.recognizer?.finish(); asr.converter = nil; asr.format = nil }
        onChange?()
    }

    func setPaused(_ paused: Bool) { isPaused = paused }

    func reportFailure(_ error: Error, callID: UUID) {
        guard self.callID == callID else { return }
        fail(error, generation: epoch)
    }

    #if DEBUG
    /// Typed tests are deliberately explicit and use the same scoring path.
    func testText(_ text: String) {
        cancel(); callID = UUID(); state = .finished
        window.commit(text); self.text = window.text
        requestScore(force: true); onChange?()
    }

    #endif

    private func receive(_ text: String, final: Bool, generation: UUID) {
        guard epoch == generation, state != .failed else { return }
        if final { window.commit(text) } else { window.updatePartial(text) }
        guard final || Date().timeIntervalSince(lastPublishTime) >= 0.4 else { return }
        self.text = window.text; lastPublishTime = Date()
        requestScore(force: final); onChange?()
    }
    private func requestScore(force: Bool) {
        let text = window.text
        guard text.split(whereSeparator: \.isWhitespace).count >= 3, text != lastRequested,
              force || Date().timeIntervalSince(lastScoreTime) >= 3 else { return }
        if scoring { pendingScore = text; return }
        score(text)
    }
    private func score(_ text: String) {
        scoring = true; lastRequested = text; lastScoreTime = Date()
        let generation = epoch, selection = scoreEpoch, model = model
        scorer.queue.async { [weak self, scorer] in
            let outcome = Result { try scorer.score(text, model: model) }
            DispatchQueue.main.async {
                guard let self else { return }
                self.scoring = false
                if self.epoch == generation, self.scoreEpoch == selection, self.state != .failed {
                    switch outcome {
                    case .success(let result): self.result = result; self.error = nil
                    case .failure(let error): self.error = error.localizedDescription
                    }
                }
                if let pending = self.pendingScore {
                    self.pendingScore = nil; self.score(pending)
                }
                self.onChange?()
            }
        }
    }
    private func fail(_ error: Error, generation: UUID) {
        guard epoch == generation else { return }
        self.error = error.localizedDescription; state = .failed
        scoreEpoch = UUID(); pendingScore = nil; result = nil
        onChange?()
    }
}

enum PipelineError: LocalizedError {
    case overloaded, invalidStream, invalidAudio, disconnected, insecureURL
    var errorDescription: String? {
        switch self {
        case .overloaded: return "Audio arrived faster than this device could transcribe. Restart analysis."
        case .invalidStream: return "The caller audio stream was invalid or incomplete."
        case .invalidAudio: return "The audio format is unsupported."
        case .disconnected: return "The caller audio connection ended unexpectedly."
        case .insecureURL: return "Use a secure wss:// audio relay URL."
        }
    }
}
