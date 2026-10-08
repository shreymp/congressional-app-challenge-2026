import AVFoundation
import Combine
import Foundation

private final class RecognitionWorker: @unchecked Sendable {
    let queue = DispatchQueue(label: "org.scamguardian.recognition", qos: .userInitiated)
    var recognizer: VoskRecognizer?
    var converter: PCMConverter?
    private let lock = NSLock()
    private var pendingBuffers = 0
    func reserve() -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard pendingBuffers < 8 else { return false }
        pendingBuffers += 1
        return true
    }
    func release() { lock.lock(); pendingBuffers -= 1; lock.unlock() }
}

private final class JevWorker: @unchecked Sendable {
    let queue = DispatchQueue(label: "org.scamguardian.jev", qos: .utility)
    var model: JevDecisionMaker?
    var callModel: JevCallDecisionMaker?
    var callVersion: Int?
}

@MainActor
final class RecordingController: ObservableObject {
    enum State { case idle, preparing, recording, stopping }
    enum DecisionMaker: String, CaseIterable {
        case rules = "Rules", jev = "Original Jev behaviors", callV1 = "Trained Jev v1", callV2 = "Trained Jev v2 (caller)"
        var version: Int? { self == .callV1 ? 1 : self == .callV2 ? 2 : nil }
    }
    struct Log: Identifiable { let id = UUID(); let text: String }
    @Published private(set) var state: State = .idle
    @Published private(set) var logs: [Log] = []
    @Published private(set) var decisionMaker: DecisionMaker = .rules
    @Published private(set) var jevBusy = false
    private let engine = AVAudioEngine()
    private let worker = RecognitionWorker()
    private let classifier = ScamClassifier()
    private let jevWorker = JevWorker()
    private var jevEpoch = 0
    private var pendingJevText: String?
    private var lastJevAssessment: JevAssessment?
    private var lastCallAssessment: JevCallAssessment?
    private var lastJevRequestTime = Date.distantPast
    private var window = TranscriptWindow()
    private var sessionID = UUID()
    private var tapInstalled = false
    private var lastPartial = ""
    private var lastPartialTime = Date.distantPast
    private var lastAssessment: ScamClassifier.Assessment?
    private var observers: [AnyCancellable] = []

    init() {
        append("Ready. English Vosk transcription runs offline.")
        append("Rule baseline: results are indicators, not a scam probability.")
        append("Tap Record and speak near the microphone.")
        for name in [AVAudioSession.interruptionNotification, AVAudioSession.routeChangeNotification,
                     AVAudioSession.mediaServicesWereResetNotification] {
            NotificationCenter.default.publisher(for: name).receive(on: DispatchQueue.main).sink { [weak self] notification in
                guard let self, self.state != .idle else { return }
                if name == AVAudioSession.routeChangeNotification {
                    guard self.state == .recording,
                          let reasonValue = notification.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt,
                          let reason = AVAudioSession.RouteChangeReason(rawValue: reasonValue),
                          [.oldDeviceUnavailable, .newDeviceAvailable, .noSuitableRouteForCategory, .routeConfigurationChange].contains(reason) else { return }
                }
                if name == AVAudioSession.interruptionNotification,
                   (notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt) != AVAudioSession.InterruptionType.began.rawValue { return }
                self.append("Audio interrupted or input changed. Recording stopped; tap Record to restart.")
                self.stop()
            }.store(in: &observers)
        }
    }

    var buttonTitle: String {
        switch state {
        case .idle: return "Record"
        case .preparing: return "Preparing…"
        case .recording: return "Stop"
        case .stopping: return "Stopping…"
        }
    }
    var isBusy: Bool { state == .preparing || state == .stopping }
    func toggle() { if state == .recording { stop() } else if state == .idle { start() } }

    func printLastScore() {
        if decisionMaker.version != nil {
            if let last = lastCallAssessment { logCall(last) }
            if lastCallAssessment?.transcript != window.text { requestJevScore(force: true) }
            return
        }
        if decisionMaker == .jev {
            if let last = lastJevAssessment { logJev(last, prefix: "Last Jev score") }
            else { append("Jev: no completed score yet.") }
            if lastJevAssessment?.transcript != window.text { requestJevScore(force: true) }
            return
        }
        // Use the latest hypothesis even when automatic partial logging is throttled.
        let assessment = classifier.assess(window.text)
        let note = window.partial.isEmpty ? "" : " | partial transcript"
        append("Last score: \(assessment.score) | \(assessment.level.rawValue)\(note) | rule score, not a probability")
    }

    func switchDecisionMaker() {
        selectDecisionMaker(decisionMaker == .rules ? .jev : .rules)
    }

    func selectDecisionMaker(_ mode: DecisionMaker) {
        decisionMaker = mode
        jevEpoch += 1
        pendingJevText = nil
        lastJevAssessment = nil
        lastCallAssessment = nil
        lastAssessment = nil
        lastJevRequestTime = .distantPast
        if decisionMaker.version != nil {
            append("Decision maker: \(decisionMaker.rawValue). Experimental scam score; calibration uses synthetic calls.")
            requestJevScore(force: true)
        } else if decisionMaker == .jev {
            append("Decision maker: Jev (experimental, on-device). Scores are behavior estimates, not scam probabilities.")
            requestJevScore(force: true)
        } else {
            append("Decision maker: rules.")
            printLastScore()
        }
    }

    private func requestJevScore(force: Bool) {
        guard decisionMaker != .rules else { return }
        let text = window.text
        guard text.split(whereSeparator: \.isWhitespace).count >= 3 else {
            if force { append("Jev: waiting for speech.") }
            return
        }
        if !force && Date().timeIntervalSince(lastJevRequestTime) < 3 { return }
        if !force && lastJevAssessment?.transcript == text { return }
        lastJevRequestTime = Date()
        // One inference in flight, plus the newest pending window; no ASR blocking.
        if jevBusy { pendingJevText = text; return }
        runJev(text)
    }

    private func runJev(_ text: String) {
        jevBusy = true
        let epoch = jevEpoch
        let mode = decisionMaker
        append("Jev: scoring transcript…")
        jevWorker.queue.async { [weak self, jevWorker] in
            let result: Result<JevAssessment?, Error>
            var callResult: JevCallAssessment?
            do {
                if let version = mode.version {
                    jevWorker.model = nil
                    if jevWorker.callVersion != version {
                        jevWorker.callModel = nil
                        jevWorker.callVersion = nil
                        jevWorker.callModel = try JevCallDecisionMaker(version: version)
                        jevWorker.callVersion = version
                    }
                    callResult = try jevWorker.callModel?.score(text)
                    result = .success(nil)
                } else {
                jevWorker.callModel = nil
                jevWorker.callVersion = nil
                if jevWorker.model == nil { jevWorker.model = try JevDecisionMaker() }
                guard let model = jevWorker.model else { throw JevError.missingModel }
                result = .success(try model.score(text))
                }
            } catch { result = .failure(error) }
            let completedCall = callResult
            DispatchQueue.main.async {
                guard let self else { return }
                self.jevBusy = false
                if self.decisionMaker == mode, self.jevEpoch == epoch {
                    switch result {
                    case .success(let assessment):
                        if let assessment {
                            self.lastJevAssessment = assessment
                            self.logJev(assessment, prefix: "Jev result")
                        } else if let assessment = completedCall {
                            self.lastCallAssessment = assessment
                            self.logCall(assessment)
                        }
                    case .failure(let error): self.append("Jev error: \(error.localizedDescription)")
                    }
                }
                if self.decisionMaker != .rules, let pending = self.pendingJevText {
                    self.pendingJevText = nil
                    self.runJev(pending)
                }
            }
        }
    }

    func testTranscript(_ text: String) {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        if decisionMaker == .rules {
            let result = classifier.assess(text)
            append("Text test: \(result.level.rawValue) | rule score \(result.score)")
        } else {
            jevEpoch += 1
            if jevBusy { pendingJevText = text } else { runJev(text) }
        }
    }

    private func logCall(_ assessment: JevCallAssessment) {
        append("\(decisionMaker.rawValue): experimental scam score \(String(format: "%.1f", assessment.score * 100))% | \(assessment.score >= 0.5 ? "Scam predicted" : "Non-scam predicted")")
        append("Scored: \(assessment.transcript)")
        append("\(Int(assessment.latencyMS)) ms\(assessment.wasTrimmed ? ", latest 300 tokens" : "") | calibrated on synthetic calls; real-call accuracy unmeasured")
    }

    private func logJev(_ assessment: JevAssessment, prefix: String) {
        guard let strongest = assessment.strongest else { return }
        append("\(prefix): strongest behavior = \(strongest.label) \(String(format: "%.1f", strongest.probability * 100))% | experimental, not a scam probability")
        append("Jev scored: \(assessment.transcript)")
        for signal in assessment.signals {
            append("  \(signal.label): \(String(format: "%.1f", signal.probability * 100))% | insufficient evidence \(String(format: "%.1f", signal.insufficientEvidence * 100))%")
        }
        append("Jev: one batched pass, \(Int(assessment.latencyMS)) ms\(assessment.wasTrimmed ? ", transcript trimmed" : "")")
    }

    private func start() {
        state = .preparing
        sessionID = UUID()
        let id = sessionID
        window = TranscriptWindow()
        lastPartial = ""
        lastAssessment = nil
        jevEpoch += 1
        pendingJevText = nil
        lastJevAssessment = nil
        lastCallAssessment = nil
        append("Starting a new session…")
        lastJevRequestTime = .distantPast
        AVAudioSession.sharedInstance().requestRecordPermission { [weak self] allowed in
            Task { @MainActor in
                guard let self, self.sessionID == id, self.state == .preparing else { return }
                guard allowed else {
                    self.append("Microphone permission denied. Enable it in Settings → Privacy & Security → Microphone.")
                    self.state = .idle
                    return
                }
                self.prepareAudio(id: id)
            }
        }
    }

    private func prepareAudio(id: UUID) {
        do {
            let audioSession = AVAudioSession.sharedInstance()
            try audioSession.setCategory(.record, mode: .measurement)
            try audioSession.setPreferredSampleRate(16_000)
            try audioSession.setActive(true)
            let format = engine.inputNode.outputFormat(forBus: 0)
            guard format.sampleRate > 0, format.channelCount > 0 else { throw TranscriptionError.invalidAudio }
            append("Loading Vosk. Input: \(Int(format.sampleRate)) Hz → 16000 Hz mono.")
            worker.queue.async { [weak self, worker] in
                do {
                    if worker.recognizer == nil { worker.recognizer = try VoskRecognizer() }
                    try worker.recognizer?.begin()
                    worker.converter = try PCMConverter(inputFormat: format)
                    DispatchQueue.main.async { self?.beginCapture(format: format, id: id) }
                } catch {
                    DispatchQueue.main.async { self?.fail(error, id: id) }
                }
            }
        } catch { fail(error, id: id) }
    }

    private func beginCapture(format: AVAudioFormat, id: UUID) {
        guard sessionID == id, state == .preparing else { return }
        engine.inputNode.installTap(onBus: 0, bufferSize: 2048, format: format) { [weak self, worker] input, _ in
            guard worker.reserve() else {
                DispatchQueue.main.async { self?.fail(TranscriptionError.decoderFailed, id: id,
                    message: "Recognition fell behind the microphone. Recording stopped to avoid silently losing audio.") }
                return
            }
            // The engine reuses tap buffers. Copy before crossing to the worker.
            guard let copy = AVAudioPCMBuffer(pcmFormat: input.format, frameCapacity: input.frameLength) else {
                worker.release()
                DispatchQueue.main.async { self?.fail(TranscriptionError.invalidAudio, id: id) }
                return
            }
            copy.frameLength = input.frameLength
            let source = UnsafeMutableAudioBufferListPointer(input.mutableAudioBufferList)
            let target = UnsafeMutableAudioBufferListPointer(copy.mutableAudioBufferList)
            for index in source.indices {
                if let sourceData = source[index].mData, let targetData = target[index].mData {
                    memcpy(targetData, sourceData, Int(source[index].mDataByteSize))
                }
            }
            worker.queue.async {
                defer { worker.release() }
                do {
                    guard let converter = worker.converter, let recognizer = worker.recognizer else {
                        throw TranscriptionError.recognizerFailed
                    }
                    let pcm = try converter.convert(copy)
                    guard pcm.frameLength > 0 else { return }
                    let result = try recognizer.accept(pcm)
                    DispatchQueue.main.async { self?.receive(result.text, isFinal: result.isFinal, id: id) }
                } catch { DispatchQueue.main.async { self?.fail(error, id: id) } }
            }
        }
        tapInstalled = true
        do {
            engine.prepare()
            try engine.start()
            state = .recording
            append("Recording. Audio is processed in memory.")
        } catch { fail(error, id: id) }
    }

    func stop() {
        guard state == .recording || state == .preparing else { return }
        state = .stopping
        let id = sessionID
        engine.stop()
        if tapInstalled { engine.inputNode.removeTap(onBus: 0); tapInstalled = false }
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        // Drain queued PCM before final_result; next start is disabled until done.
        worker.queue.async { [weak self, worker] in
            do {
                let final = try worker.recognizer?.finish() ?? ""
                worker.converter = nil
                DispatchQueue.main.async {
                    guard let self, self.sessionID == id else { return }
                    self.receive(final, isFinal: true, id: id)
                    self.append("Stopped. Final window: \(self.window.finalized.isEmpty ? "(no speech recognized)" : self.window.finalized)")
                    self.state = .idle
                }
            } catch {
                DispatchQueue.main.async {
                    guard let self, self.sessionID == id else { return }
                    self.append("Error: \(error.localizedDescription)")
                    self.state = .idle
                }
            }
        }
    }

    private func fail(_ error: Error, id: UUID, message: String? = nil) {
        guard sessionID == id, state == .preparing || state == .recording else { return }
        append(message ?? "Error: \(error.localizedDescription)")
        stop()
    }

    private func receive(_ text: String, isFinal: Bool, id: UUID) {
        guard sessionID == id, state != .idle else { return }
        processTranscript(text, isFinal: isFinal)
    }

    func processTranscript(_ text: String, isFinal: Bool) {
        if isFinal {
            window.commit(text)
            lastPartial = ""
            if !text.isEmpty { append("Text: \(text)") }
        } else {
            window.updatePartial(text)
            guard text != lastPartial, Date().timeIntervalSince(lastPartialTime) >= 0.8 else { return }
            lastPartial = text
            lastPartialTime = Date()
            if !text.isEmpty { append("Partial: \(text)") }
        }
        if decisionMaker != .rules {
            requestJevScore(force: isFinal)
            return
        }
        let assessment = classifier.assess(window.text)
        if isFinal || assessment != lastAssessment {
            append("\(isFinal ? "Result" : "Preview"): \(assessment.level.rawValue) | rule score \(assessment.score)")
            for signal in assessment.signals {
                append("  \(signal.label) (+\(signal.weight)): \"\(signal.evidence)\"")
            }
            lastAssessment = assessment
        }
    }

    private func append(_ message: String) {
        let timestamp = Date().formatted(date: .omitted, time: .standard)
        logs.append(Log(text: "[\(timestamp)] \(message)"))
        if logs.count > 200 { logs.removeFirst(logs.count - 200) }
    }
}
