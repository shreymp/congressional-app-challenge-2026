#if DEBUG
import AVFoundation
import Combine
import Foundation

@MainActor
final class TranscriptTestSource: ObservableObject {
    let pipeline: TranscriptPipeline
    @Published private(set) var running = false
    private let engine = AVAudioEngine()
    private var tap = false
    private var fileTask: Task<Void, Never>?
    private var id: UUID?
    private var observers: [AnyCancellable] = []
    init(pipeline: TranscriptPipeline) {
        self.pipeline = pipeline
        for name in [AVAudioSession.interruptionNotification, AVAudioSession.routeChangeNotification,
                     AVAudioSession.mediaServicesWereResetNotification] {
            NotificationCenter.default.publisher(for: name).receive(on: DispatchQueue.main).sink { [weak self] _ in
                guard let self, self.running, self.tap else { return }
                self.stop()
            }.store(in: &observers)
        }
    }
    func record() async {
        guard !running else { return }
        running = true
        let id = UUID(); self.id = id
        let permitted = await withCheckedContinuation { continuation in
            AVAudioSession.sharedInstance().requestRecordPermission { continuation.resume(returning: $0) }
        }
        guard self.id == id else { return }
        pipeline.begin(callID: id)
        guard permitted else { pipeline.reportFailure(PhoneError.microphoneDenied, callID: id); running = false; return }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .measurement)
            try session.setActive(true)
            let input = engine.inputNode, format = input.outputFormat(forBus: 0)
            guard format.sampleRate > 0, format.channelCount > 0 else { throw PipelineError.invalidAudio }
            input.installTap(onBus: 0, bufferSize: 2048, format: format) { [weak self] buffer, _ in
                // The engine owns its buffer only during this callback.
                guard let owned = Self.copy(buffer) else { return }
                Task { @MainActor in
                    guard let self, self.id == id, self.running else { return }
                    self.pipeline.accept(owned, callID: id)
                    if self.pipeline.state == .failed { self.stop() }
                }
            }
            tap = true; engine.prepare(); try engine.start()
        } catch { pipeline.reportFailure(error, callID: id); stop() }
    }
    func playFile(_ url: URL) {
        guard !running else { return }
        let id = UUID(); self.id = id; running = true; pipeline.begin(callID: id)
        fileTask = Task { [weak self] in
            let access = url.startAccessingSecurityScopedResource()
            defer { if access { url.stopAccessingSecurityScopedResource() } }
            do {
                let file = try AVAudioFile(forReading: url)
                // Bound import work and accidental very large recordings to five minutes.
                guard Double(file.length) / file.processingFormat.sampleRate <= 300 else { throw PipelineError.invalidAudio }
                while file.framePosition < file.length {
                    guard !Task.isCancelled, let self, self.id == id else { return }
                    guard let buffer = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: 2048) else { throw PipelineError.invalidAudio }
                    try file.read(into: buffer)
                    self.pipeline.accept(buffer, callID: id)
                    await self.pipeline.drainAudio()
                    guard self.pipeline.state != .failed else { self.stop(); return }
                }
                self?.stop()
            } catch {
                self?.pipeline.reportFailure(error, callID: id); self?.stop()
            }
        }
    }
    func stop() {
        fileTask?.cancel(); fileTask = nil
        engine.stop()
        if tap {
            engine.inputNode.removeTap(onBus: 0); tap = false
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        }
        if let id { pipeline.finish(callID: id) }
        id = nil; running = false
    }
    nonisolated static func copy(_ buffer: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        guard let result = AVAudioPCMBuffer(pcmFormat: buffer.format, frameCapacity: buffer.frameLength) else { return nil }
        result.frameLength = buffer.frameLength
        let source = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: buffer.audioBufferList))
        let destination = UnsafeMutableAudioBufferListPointer(result.mutableAudioBufferList)
        for (src, dst) in zip(source, destination) {
            guard let from = src.mData, let to = dst.mData else { return nil }
            memcpy(to, from, Int(src.mDataByteSize))
        }
        return result
    }
    deinit { fileTask?.cancel(); engine.stop(); if tap { engine.inputNode.removeTap(onBus: 0) } }
}

#endif
