import AVFAudio
import Foundation

enum CallingEvent {
    case connected(UUID, Date)
    case ended(UUID, PhoneCallOutcome, Date)
    case assessmentStarted(UUID)
    case assessed(UUID, Voice)
    case failed(UUID, String)
    /// Owned remote-caller PCM, never the local microphone or mixed speakers.
    case callerAudio(UUID, AVAudioPCMBuffer)
    /// An authenticated per-call relay subscription, emitted after connected.
    case callerStream(UUID, CallerStreamConfiguration)
    case analysisFailed(UUID, String)
}

/// Implement with the future signaling/media provider. Emitting `connected` must
/// mean media is actually connected. Assessment events must refer to that call's
/// remote media stream; they must never contain a sample or locally timed result.
/// `start` returns after signaling is accepted; `answer` waits until the incoming
/// session is ready to connect (including any concurrent `prepareIncoming`). Audio
/// starts only in `activateAudio`; reset/end must cancel all work for that call.
/// Emit callerAudio from a Twilio custom audio renderer, or callerStream for
/// a Media Streams relay. Use only one input for each call. Jev stays on-device.
@MainActor
protocol CallingBackend: AnyObject {
    var isConfigured: Bool { get }
    var onEvent: ((CallingEvent) -> Void)? { get set }
    func start(callID: UUID, number: String) async throws
    func prepareIncoming(callID: UUID, number: String) async throws
    func answer(callID: UUID) async throws
    func end(callID: UUID) async throws
    func setMuted(_ muted: Bool, callID: UUID) async throws
    func setHeld(_ held: Bool, callID: UUID) async throws
    func sendDTMF(_ digits: String, callID: UUID) async throws
    func registerVoIPToken(_ token: Data?) async throws
    func activateAudio(_ session: AVAudioSession)
    func deactivateAudio(_ session: AVAudioSession)
    func reset()
    /// Provider-specific PushKit payloads must be decoded by their SDK, then
    /// immediately reported to CallKit through reportIncoming before completion.
    func handleVoIPPush(_ payload: [AnyHashable: Any], reportIncoming: @escaping (UUID, String, @escaping () -> Void) -> Void,
                       completion: @escaping () -> Void) -> Bool
}

extension CallingBackend {
    func handleVoIPPush(_ payload: [AnyHashable: Any], reportIncoming: @escaping (UUID, String, @escaping () -> Void) -> Void,
                       completion: @escaping () -> Void) -> Bool { false }
}

@MainActor
final class UnconnectedCallingBackend: CallingBackend {
    var isConfigured: Bool { false }
    var onEvent: ((CallingEvent) -> Void)?
    func start(callID: UUID, number: String) async throws { throw PhoneError.serviceUnavailable }
    func prepareIncoming(callID: UUID, number: String) async throws { throw PhoneError.serviceUnavailable }
    func answer(callID: UUID) async throws { throw PhoneError.serviceUnavailable }
    func end(callID: UUID) async throws { throw PhoneError.serviceUnavailable }
    func setMuted(_ muted: Bool, callID: UUID) async throws { throw PhoneError.serviceUnavailable }
    func setHeld(_ held: Bool, callID: UUID) async throws { throw PhoneError.serviceUnavailable }
    func sendDTMF(_ digits: String, callID: UUID) async throws { throw PhoneError.serviceUnavailable }
    func registerVoIPToken(_ token: Data?) async throws { throw PhoneError.serviceUnavailable }
    func activateAudio(_ session: AVAudioSession) {}
    func deactivateAudio(_ session: AVAudioSession) {}
    func reset() {}
}

struct VoicemailMessage: Identifiable, Equatable {
    let id: String
    let caller: Person
    let date: Date
    let duration: Int
    let isRead: Bool
    let audioURL: URL
}

@MainActor
protocol VoicemailBackend {
    var isConfigured: Bool { get }
    func messages() async throws -> [VoicemailMessage]
    func markRead(id: String) async throws
    func delete(id: String) async throws
}

@MainActor
struct UnconnectedVoicemailBackend: VoicemailBackend {
    var isConfigured: Bool { false }
    func messages() async throws -> [VoicemailMessage] { throw PhoneError.serviceUnavailable }
    func markRead(id: String) async throws { throw PhoneError.serviceUnavailable }
    func delete(id: String) async throws { throw PhoneError.serviceUnavailable }
}

/// Replace these factories when the authenticated signaling/media and voicemail
/// services are available. Production never falls back to the demo's sample data.
@MainActor
enum AppServices {
    static func makeCallingBackend() -> CallingBackend {
        guard let url = CallingConnection.serverURL, let credential = CallingConnection.token else { return UnconnectedCallingBackend() }
        return TwilioCallingBackend(client: CallingServiceClient(baseURL: url, credential: credential))
    }
    static func makeVoicemailBackend() -> VoicemailBackend { UnconnectedVoicemailBackend() }
}
