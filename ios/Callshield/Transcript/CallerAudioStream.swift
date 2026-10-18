import AVFoundation
import Foundation

/// Twilio labels tracks relative to the streamed call leg, not the app user.
/// The signaling owner must choose the track that actually contains the caller.
struct CallerStreamConfiguration {
    let url: URL
    let bearerToken: String
    let callerTrack: String
    let callSID: String
}

struct TwilioMediaDecoder {
    enum Output { case audio(AVAudioPCMBuffer), ended, none }
    let callerTrack: String
    let expectedCallSID: String
    private(set) var streamSID: String?
    private var lastChunk = 0
    private var stopped = false
    init(callerTrack: String, expectedCallSID: String) {
        self.callerTrack = callerTrack
        self.expectedCallSID = expectedCallSID
    }

    mutating func decode(_ data: Data) throws -> Output {
        guard data.count <= 64_000, !stopped,
              let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let event = json["event"] as? String else { throw PipelineError.invalidStream }
        switch event {
        case "connected": return .none
        case "start":
            guard streamSID == nil, ["inbound", "outbound"].contains(callerTrack),
                  let start = json["start"] as? [String: Any],
                  start["callSid"] as? String == expectedCallSID,
                  let sid = start["streamSid"] as? String, !sid.isEmpty,
                  json["streamSid"] as? String == sid,
                  let tracks = start["tracks"] as? [String], tracks.contains(callerTrack),
                  let format = start["mediaFormat"] as? [String: Any],
                  format["encoding"] as? String == "audio/x-mulaw",
                  format["sampleRate"] as? Int == 8000, format["channels"] as? Int == 1 else {
                throw PipelineError.invalidStream
            }
            streamSID = sid; return .none
        case "media":
            guard let streamSID, json["streamSid"] as? String == streamSID,
                  let media = json["media"] as? [String: Any],
                  let track = media["track"] as? String, ["inbound", "outbound"].contains(track) else {
                throw PipelineError.invalidStream
            }
            guard track == callerTrack else { return .none }
            guard let chunkString = media["chunk"] as? String, let chunk = Int(chunkString), chunk > 0 else {
                throw PipelineError.invalidStream
            }
            if chunk <= lastChunk { return .none } // Duplicates never repeat transcript text.
            guard chunk == lastChunk + 1,
                  let payload = media["payload"] as? String, let bytes = Data(base64Encoded: payload),
                  !bytes.isEmpty, bytes.count <= 8000 else { throw PipelineError.invalidStream }
            lastChunk = chunk
            return .audio(try Self.muLawPCM(bytes))
        case "stop":
            guard let streamSID, json["streamSid"] as? String == streamSID else { throw PipelineError.invalidStream }
            stopped = true; return .ended
        default: throw PipelineError.invalidStream
        }
    }

    static func expandMuLaw(_ byte: UInt8) -> Int16 {
        let value = Int(~byte)
        let magnitude = (((value & 0x0f) << 3) + 0x84) << ((value & 0x70) >> 4)
        return Int16((value & 0x80) != 0 ? 0x84 - magnitude : magnitude - 0x84)
    }
    static func muLawPCM(_ bytes: Data) throws -> AVAudioPCMBuffer {
        guard let format = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 8000, channels: 1, interleaved: true),
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(bytes.count)),
              let samples = buffer.int16ChannelData?[0] else { throw PipelineError.invalidAudio }
        buffer.frameLength = AVAudioFrameCount(bytes.count)
        for (index, byte) in bytes.enumerated() { samples[index] = expandMuLaw(byte) }
        return buffer
    }
}

/// Connects to OUR authenticated relay, not Twilio's server-facing Stream URL.
/// Token and audio stay in memory; no transcript or Jev inference goes to the server.
@MainActor
final class CallerAudioStream {
    private var task: Task<Void, Never>?
    private var socket: URLSessionWebSocketTask?
    private var session: URLSession?
    func connect(_ config: CallerStreamConfiguration, callID: UUID, pipeline: TranscriptPipeline) throws {
        disconnect()
        let local = ["localhost", "127.0.0.1", "::1"].contains(config.url.host ?? "")
        var allowed = config.url.scheme == "wss"
        #if DEBUG
        allowed = allowed || (local && config.url.scheme == "ws")
        #endif
        guard allowed, config.url.host != nil, config.url.user == nil, config.url.password == nil,
              !config.bearerToken.isEmpty, !config.callSID.isEmpty else { throw PipelineError.insecureURL }
        var request = URLRequest(url: config.url)
        request.setValue("Bearer \(config.bearerToken)", forHTTPHeaderField: "Authorization")
        let session = URLSession(configuration: .ephemeral)
        let socket = session.webSocketTask(with: request)
        socket.maximumMessageSize = 64_000
        self.session = session; self.socket = socket
        socket.resume()
        task = Task { [weak self, weak pipeline] in
            var decoder = TwilioMediaDecoder(callerTrack: config.callerTrack, expectedCallSID: config.callSID)
            do {
                while !Task.isCancelled {
                    let message = try await socket.receive()
                    guard !Task.isCancelled, let pipeline, pipeline.callID == callID else { return }
                    let data: Data
                    switch message {
                    case .string(let text): data = Data(text.utf8)
                    case .data(let bytes): data = bytes
                    @unknown default: throw PipelineError.invalidStream
                    }
                    switch try decoder.decode(data) {
                    case .audio(let buffer): pipeline.accept(buffer, callID: callID)
                    case .ended: pipeline.finish(callID: callID); self?.disconnect(); return
                    case .none: break
                    }
                    if pipeline.state == .failed { self?.disconnect(); return }
                }
            } catch {
                guard !Task.isCancelled else { return }
                pipeline?.reportFailure(error, callID: callID)
                self?.disconnect()
            }
        }
    }
    func disconnect() {
        task?.cancel(); task = nil
        socket?.cancel(with: .goingAway, reason: nil); socket = nil
        session?.invalidateAndCancel(); session = nil
    }
    deinit { task?.cancel(); socket?.cancel(with: .goingAway, reason: nil); session?.invalidateAndCancel() }
}
