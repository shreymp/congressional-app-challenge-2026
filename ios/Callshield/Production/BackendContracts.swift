import AVFAudio
import Foundation

enum CallingEvent {
    case connected(UUID, Date)
    case ended(UUID, PhoneCallOutcome, Date)
    case assessmentStarted(UUID)
    case assessed(UUID, Voice)
    case failed(UUID, String)
    /// A call is waiting for this phone: its call UUID, the caller's number as the service
    /// saw it (may be empty) and an optional caller name. Only backends that ring without
    /// PushKit emit this; the coordinator reports it to CallKit.
    case incoming(UUID, String, String?)
    /// A backend that rings without PushKit cannot wait for calls and trying again will not
    /// help (its access was refused or has expired). The text is shown to the person using
    /// the phone. Temporary failures such as no network are retried quietly and not reported.
    case incomingCallsUnavailable(String)
}

/// Implement with the signaling/media provider; `LiveKitCallingBackend` is the LiveKit
/// implementation. Emitting `connected` must
/// mean media is actually connected. Assessment events must refer to that call's
/// remote media stream; they must never contain a sample or locally timed result.
/// `start` returns after signaling is accepted; `answer` waits until the incoming
/// session is ready to connect (including any concurrent `prepareIncoming`). Audio
/// starts only in `activateAudio`; reset/end must cancel all work for that call.
///
/// Incoming calls arrive one of two ways. A backend with `usesVoIPPush` is woken by
/// PushKit. A backend without it is told to `listenForIncomingCalls` while the app is
/// open and emits `incoming`; `prepareIncoming` follows once CallKit accepts the call.
/// `end` for a call that was announced but never rang (CallKit refused it, or another
/// call was active) only makes the backend forget that call.
@MainActor
protocol CallingBackend: AnyObject {
    var isConfigured: Bool { get }
    /// True when incoming calls reach the app as PushKit VoIP pushes. When false the
    /// coordinator never creates a PKPushRegistry, which needs the push entitlement.
    var usesVoIPPush: Bool { get }
    /// False for an inbound-only service; outgoing calls then stay with the system dialer.
    var canPlaceOutgoingCalls: Bool { get }
    /// False when the service cannot hold a call or send keypad tones. The in-call screen then
    /// leaves those two controls out instead of offering buttons that can only fail.
    var supportsHoldAndKeypad: Bool { get }
    var onEvent: ((CallingEvent) -> Void)? { get set }
    /// Called at launch and every time the app returns to the foreground.
    func listenForIncomingCalls()
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
}

@MainActor
final class UnconnectedCallingBackend: CallingBackend {
    var isConfigured: Bool { false }
    var usesVoIPPush: Bool { false }
    var canPlaceOutgoingCalls: Bool { false }
    var supportsHoldAndKeypad: Bool { false }
    var onEvent: ((CallingEvent) -> Void)?
    func listenForIncomingCalls() {}
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

/// Calling uses LiveKit once CALLSHIELD_LIVEKIT_HOST and CALLSHIELD_LOBBY_TOKEN are set in
/// the gitignored Configuration/Local.xcconfig. Replace the voicemail factory when that
/// service is available. Production never falls back to the demo's sample data.
@MainActor
enum AppServices {
    static func makeCallingBackend() -> CallingBackend {
        // Tests never open a network connection, even on a Mac whose Local.xcconfig is filled in.
        if ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil
            || NSClassFromString("XCTestCase") != nil { return UnconnectedCallingBackend() }
        #if DEBUG
        let arguments = ProcessInfo.processInfo.arguments
        if arguments.contains("--ui-test-demo") || arguments.contains("--ui-test-production") { return UnconnectedCallingBackend() }
        #endif
        guard let host = AppConfiguration.liveKitHost, let lobbyToken = AppConfiguration.lobbyToken else {
            return UnconnectedCallingBackend()
        }
        return LiveKitCallingBackend(host: host, lobbyToken: lobbyToken)
    }
    static func makeVoicemailBackend() -> VoicemailBackend { UnconnectedVoicemailBackend() }
}
