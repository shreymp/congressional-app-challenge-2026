import AVFAudio
import Foundation
import LiveKit
import UIKit

/// Every audio-engine change runs on this one serial queue. `setEngineAvailability` blocks
/// its caller until WebRTC has applied it, so it must never run on the main thread.
private let liveKitAudioQueue = DispatchQueue(label: "org.callshield.livekit.audio")

private func callshieldLog(_ message: String) { print("[Callshield] \(message)") }

/// For the log only. The SDK's own description of an error can read just "Unknown", so its
/// code goes with it; the person on the call is never shown this text.
private func callshieldDetail(_ error: Error) -> String {
    guard let error = error as? LiveKitError else { return error.localizedDescription }
    return "\(error.localizedDescription) [LiveKit error \(error.type.rawValue)]"
}

/// What the person on the call sees when joining the call room or publishing the microphone
/// fails, in place of the SDK's own wording (that goes to the log).
private struct CallConnectionError: LocalizedError {
    var errorDescription: String? { "The call could not be connected." }
}

/// The "incoming call" message the scam-guard agent sends to the lobby room. It carries a
/// join token, so never print one.
struct IncomingCallInvite: Equatable {
    static let topic = "callshield.incoming"
    let callID: UUID
    let room: String
    let token: String
    let handle: String
    let callerIdentity: String
    let callerName: String?

    /// nil unless the payload is a complete invite. A missing or empty `handle` is accepted:
    /// a caller who withholds their number must still ring.
    static func decode(_ data: Data) -> IncomingCallInvite? {
        guard let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              object["type"] as? String == "incoming_call",
              let callID = (object["callUUID"] as? String).flatMap(UUID.init(uuidString:)),
              let room = object["room"] as? String, !room.isEmpty,
              let token = object["token"] as? String, !token.isEmpty,
              let callerIdentity = object["callerIdentity"] as? String, !callerIdentity.isEmpty else { return nil }
        let name = (object["callerName"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return IncomingCallInvite(callID: callID, room: room, token: token, handle: object["handle"] as? String ?? "",
                                  callerIdentity: callerIdentity, callerName: name.isEmpty ? nil : String(name.prefix(128)))
    }
}

/// Foreground-only ringing over LiveKit, with no PushKit. While the app is open it waits in a
/// small "lobby" room for an invite from the scam-guard agent. CallKit then rings, the app
/// joins the call room silently, and the microphone is published only when the call is
/// answered: for a LiveKit phone call, publishing audio is what answers it.
@MainActor
final class LiveKitCallingBackend: NSObject, CallingBackend, RoomDelegate {
    private struct LiveCall {
        let invite: IncomingCallInvite
        let prepare: Task<Void, Error>
        var room: Room?
        var answered = false     // microphone published
        var audioActive = false  // engine running inside CallKit's activation window
        var connected = false    // `connected` already emitted
        var connectedAt: Date?
        var detector = DeepfakeMonitor()
    }

    let isConfigured: Bool
    var usesVoIPPush: Bool { false }
    var canPlaceOutgoingCalls: Bool { false }
    /// The call-room token has no data grant, so keypad tones would be dropped, and a phone call has no hold.
    var supportsHoldAndKeypad: Bool { false }
    var onEvent: ((CallingEvent) -> Void)?

    private let serverURL: String
    private let lobbyToken: String
    private var listening = false
    private var lobbyRejected = false // The service refused the lobby token: no retry until the next foreground.
    private var announcedRejection = false
    private var lobbyRoom: Room?
    private var lobbyConnect: Task<Void, Never>?
    private var lobbyRetry: Task<Void, Never>?
    private var invites: [UUID: IncomingCallInvite] = [:]
    private var handledCallIDs: [UUID] = []
    private var call: LiveCall?
    private var callTeardown: Task<Void, Never>?
    private var assessmentWatchdog: Task<Void, Never>?
    private var observers: [NSObjectProtocol] = []
    private var idleTimerWasDisabled: Bool?
    private var askedForMicrophone = false

    init(host: String, lobbyToken: String) {
        serverURL = "wss://" + host
        self.lobbyToken = lobbyToken
        isConfigured = !host.isEmpty && !lobbyToken.isEmpty
        super.init()
        guard isConfigured else { return }
        // LiveKit's CallKit rule: before any Room exists, stop the SDK configuring AVAudioSession
        // and hold its audio engine off. Rooms are created only after `audioQueueDrained()`.
        liveKitAudioQueue.async {
            AudioManager.shared.audioSession.isAutomaticConfigurationEnabled = false
            do { try AudioManager.shared.setEngineAvailability(.none) }
            catch { callshieldLog("could not hold the audio engine off: \(callshieldDetail(error))") }
        }
        let center = NotificationCenter.default
        observers = [
            center.addObserver(forName: UIApplication.didBecomeActiveNotification, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in self?.appBecameActive() }
            },
            // Not willResignActive: CallKit's incoming-call UI makes the app inactive while it rings.
            center.addObserver(forName: UIApplication.didEnterBackgroundNotification, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in self?.appEnteredBackground() }
            }
        ]
    }

    deinit { for observer in observers { NotificationCenter.default.removeObserver(observer) } }

    // MARK: - Listening

    func listenForIncomingCalls() {
        guard isConfigured else { return }
        listening = true
        guard UIApplication.shared.applicationState != .background else { return }
        // Keeping the screen awake is what makes a foreground-only ring usable for the demo.
        if idleTimerWasDisabled == nil {
            idleTimerWasDisabled = UIApplication.shared.isIdleTimerDisabled
            UIApplication.shared.isIdleTimerDisabled = true
        }
        askForMicrophoneOnce()
        lobbyRejected = false // In the foreground again: a refused token gets one more try.
        lobbyRetry?.cancel(); lobbyRetry = nil // Try now, not after the delay.
        connectLobbyIfNeeded()
    }

    /// Asked while the app is in front, because the prompt cannot appear later over the incoming-call UI.
    private func askForMicrophoneOnce() {
        guard !askedForMicrophone, UIApplication.shared.applicationState == .active,
              AVAudioSession.sharedInstance().recordPermission == .undetermined else { return }
        askedForMicrophone = true
        AVAudioSession.sharedInstance().requestRecordPermission { _ in }
    }

    private func appBecameActive() {
        if listening { listenForIncomingCalls() }
    }

    private func appEnteredBackground() {
        if let previous = idleTimerWasDisabled {
            UIApplication.shared.isIdleTimerDisabled = previous
            idleTimerWasDisabled = nil
        }
        // A ringing or connected call carries on in the background; only the idle lobby is dropped.
        guard call == nil, invites.isEmpty else { return }
        Task { @MainActor in
            await self.stopLobby()
            self.connectLobbyIfNeeded() // Does nothing unless the app is already back in front.
        }
    }

    // MARK: - Lobby

    private var wantsLobby: Bool {
        listening && !lobbyRejected && call == nil && invites.isEmpty && UIApplication.shared.applicationState != .background
    }

    private func connectLobbyIfNeeded() {
        guard wantsLobby, lobbyRoom == nil, lobbyConnect == nil, lobbyRetry == nil else { return }
        lobbyConnect = Task { @MainActor [weak self] in
            await self?.connectLobby()
            self?.lobbyConnect = nil
            self?.connectLobbyIfNeeded() // The app may have come back while a stopped attempt was unwinding.
        }
    }

    private func connectLobby() async {
        _ = await callTeardown?.value // One Room at a time: the last call room finishes disconnecting first.
        await audioQueueDrained()
        guard wantsLobby, lobbyRoom == nil else { return }
        let room = Room()
        room.add(delegate: self)
        lobbyRoom = room
        do {
            // Signalling only: nothing in the lobby is subscribed to or published.
            try await room.connect(url: serverURL, token: lobbyToken, connectOptions: ConnectOptions(autoSubscribe: false))
        } catch {
            guard lobbyRoom === room else { return } // stopLobby() got there first.
            lobbyRoom = nil
            if (error as? LiveKitError)?.type == .validation {
                // The service answered 4xx: the token is expired or wrong, and trying again cannot help. Because
                // wantsLobby is now false, connectLobbyIfNeeded() stops here too; the next foreground tries once more.
                lobbyRejected = true
                callshieldLog("lobby token refused: \(callshieldDetail(error))")
                if !announcedRejection { // Once, not on every foreground; a later successful connection re-arms it.
                    announcedRejection = true
                    onEvent?(.incomingCallsUnavailable("Callshield can’t take incoming calls right now: its access to the calling service was refused or has expired. It needs to be set up again."))
                }
                return
            }
            callshieldLog("lobby connection failed: \(callshieldDetail(error))")
            scheduleLobbyRetry()
            return
        }
        guard lobbyRoom === room else { await room.disconnect(); return }
        announcedRejection = false
        callshieldLog("lobby connected; waiting for incoming calls")
    }

    private func stopLobby() async {
        lobbyRetry?.cancel(); lobbyRetry = nil
        guard let room = lobbyRoom else { return }
        lobbyRoom = nil
        await room.disconnect()
        callshieldLog("lobby disconnected")
    }

    private func scheduleLobbyRetry() {
        guard wantsLobby, lobbyRetry == nil else { return }
        lobbyRetry = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            guard !Task.isCancelled, let self else { return }
            self.lobbyRetry = nil
            self.connectLobbyIfNeeded()
        }
    }

    /// Resumes after everything queued so far on the audio queue has run, which includes the
    /// engine being held off in `init`. Awaited before every `Room()`.
    private func audioQueueDrained() async {
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            liveKitAudioQueue.async { continuation.resume() }
        }
    }

    // MARK: - Invites

    private func receiveInvite(_ data: Data, in room: Room) {
        guard room === lobbyRoom, let onEvent else { return }
        guard let invite = IncomingCallInvite.decode(data) else { callshieldLog("ignored a malformed invite"); return }
        // The agent repeats an invite every few seconds until the call is joined or over.
        guard !handledCallIDs.contains(invite.callID), call == nil, invites.isEmpty else { return }
        handledCallIDs.append(invite.callID)
        if handledCallIDs.count > 32 { handledCallIDs.removeFirst() }
        invites[invite.callID] = invite
        callshieldLog("invite received: call \(invite.callID), handle \"\(invite.handle)\"")
        onEvent(.incoming(invite.callID, invite.handle, invite.callerName))
    }

    private func preparation(for callID: UUID) throws -> Task<Void, Error> {
        if let current = call, current.invite.callID == callID { return current.prepare }
        guard call == nil, let invite = invites.removeValue(forKey: callID) else { throw PhoneError.serviceUnavailable }
        callshieldLog("CallKit is ringing; joining call room \(invite.room) silently")
        let prepare = Task<Void, Error> { @MainActor [weak self] in
            guard let self else { throw CancellationError() }
            try await self.join(invite)
        }
        call = LiveCall(invite: invite, prepare: prepare)
        return prepare
    }

    /// A silent join: no microphone and the engine held off, so the phone caller keeps hearing
    /// ringback. Publishing audio here would answer the phone call.
    private func join(_ invite: IncomingCallInvite) async throws {
        await stopLobby() // The lobby and a call room are never connected at the same time.
        await audioQueueDrained()
        guard call?.invite.callID == invite.callID else { throw CancellationError() }
        let room = Room()
        room.add(delegate: self)
        call?.room = room
        do {
            try await room.connect(url: serverURL, token: invite.token,
                                   connectOptions: ConnectOptions(autoSubscribe: true, enableMicrophone: false))
        } catch {
            guard call?.invite.callID == invite.callID else { throw error } // Ended while connecting: not a failure.
            callshieldLog("joining the call room failed: \(callshieldDetail(error))")
            throw CallConnectionError()
        }
        // Ended while connecting: closeCall() disconnects this room once this task has finished.
        guard call?.invite.callID == invite.callID else { throw CancellationError() }
        callshieldLog("joined call room")
        // People already in a room are not announced with participantDidConnect, so look.
        if await callerHasLeft(invite, from: room) { callEnded("the caller hung up before this phone joined") }
    }

    private func callerIsPresent(in room: Room, identity: String) -> Bool {
        room.remoteParticipants.values.contains { $0.identity?.stringValue == identity }
    }

    /// The SDK fills `remoteParticipants` from the join response in a task that `connect()` and a
    /// full reconnect do not wait for, so a caller who is not listed yet is looked for once more
    /// a moment later. A caller who really left ends the call one second later than it could.
    private func callerHasLeft(_ invite: IncomingCallInvite, from room: Room) async -> Bool {
        guard !callerIsPresent(in: room, identity: invite.callerIdentity) else { return false }
        try? await Task.sleep(nanoseconds: 1_000_000_000) // Returns early when closeCall() cancels this task.
        return call?.invite.callID == invite.callID && call?.room === room
            && !callerIsPresent(in: room, identity: invite.callerIdentity)
    }

    // MARK: - CallingBackend

    func start(callID: UUID, number: String) async throws {
        // LiveKit-rented numbers are inbound-only; outgoing calls stay with the system dialer.
        throw PhoneError.serviceUnavailable
    }

    func prepareIncoming(callID: UUID, number: String) async throws {
        try await preparation(for: callID).value
    }

    func answer(callID: UUID) async throws {
        try await preparation(for: callID).value // Waits for the silent join, starting it if needed.
        guard let current = call, current.invite.callID == callID, let room = current.room else { throw PhoneError.actionUnavailable }
        // The engine is still held off, so this publishes without capturing. Audio starts in activateAudio.
        do { try await room.localParticipant.setMicrophone(enabled: true) }
        catch {
            guard call?.invite.callID == callID else { throw PhoneError.actionUnavailable } // Ended meanwhile.
            callshieldLog("publishing the microphone failed: \(callshieldDetail(error))")
            throw CallConnectionError()
        }
        guard call?.invite.callID == callID else { throw PhoneError.actionUnavailable }
        call?.answered = true
        callshieldLog("answered: microphone published")
        announceConnectedIfReady()
    }

    func end(callID: UUID) async throws {
        invites[callID] = nil // Announced but never rung: CallKit refused it or another call was active.
        guard call?.invite.callID == callID else { connectLobbyIfNeeded(); return }
        closeCall()
        callshieldLog("ended by this phone")
    }

    func setMuted(_ muted: Bool, callID: UUID) async throws {
        guard let current = call, current.invite.callID == callID, current.answered, let room = current.room else {
            throw PhoneError.actionUnavailable
        }
        // On an existing publication this mutes or unmutes; it never unpublishes.
        try await room.localParticipant.setMicrophone(enabled: !muted)
    }

    func setHeld(_ held: Bool, callID: UUID) async throws { throw PhoneError.actionUnavailable }

    func sendDTMF(_ digits: String, callID: UUID) async throws {
        guard let current = call, current.invite.callID == callID, current.answered, let room = current.room,
              // The server silently drops keypad tones sent with a token that may not publish data.
              room.localParticipant.permissions.canPublishData else { throw PhoneError.actionUnavailable }
        for digit in digits {
            // RFC 4733 event codes, as in publishDtmf's documentation: 0-9, then * is 10 and # is 11.
            let code: UInt32
            switch digit {
            case "*": code = 10
            case "#": code = 11
            default:
                guard digit.isASCII, let value = digit.wholeNumberValue else { throw PhoneError.actionUnavailable }
                code = UInt32(value)
            }
            try await room.localParticipant.publishDtmf(code: code, digit: String(digit))
        }
    }

    func registerVoIPToken(_ token: Data?) async throws {} // No PushKit in this build.

    func activateAudio(_ session: AVAudioSession) {
        guard let callID = call?.invite.callID else { return }
        liveKitAudioQueue.async {
            do {
                // CallKit has already activated the session, so never call setActive here.
                // Same options as PhoneCallCoordinator.
                try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.allowBluetoothHFP])
                try AudioManager.shared.setEngineAvailability(.default)
                Task { @MainActor in self.audioActivated(for: callID) }
            } catch {
                let detail = callshieldDetail(error)
                Task { @MainActor in self.audioFailed(for: callID, detail: detail) }
            }
        }
    }

    func deactivateAudio(_ session: AVAudioSession) {
        call?.audioActive = false
        liveKitAudioQueue.async { try? AudioManager.shared.setEngineAvailability(.none) }
    }

    func reset() {
        invites.removeAll()
        if closeCall() != nil { callshieldLog("call reset") } else { connectLobbyIfNeeded() }
    }

    // MARK: - Call state

    private func audioActivated(for callID: UUID) {
        guard call?.invite.callID == callID else { return }
        call?.audioActive = true
        callshieldLog("audio activated")
        announceConnectedIfReady()
    }

    private func audioFailed(for callID: UUID, detail: String) {
        guard call?.invite.callID == callID else { return }
        callFailed("Audio could not start.", detail: detail)
    }

    /// `connected` means real media: the microphone is published and the engine is running
    /// inside CallKit's activation window. The two can finish in either order.
    private func announceConnectedIfReady() {
        guard let current = call, current.answered, current.audioActive, !current.connected else { return }
        call?.connected = true
        callshieldLog("connected")
        let now = Date()
        call?.connectedAt = now
        onEvent?(.connected(current.invite.callID, now))
        onEvent?(.deepfakeAssessment(current.invite.callID, DeepfakeAssessment(state: .waiting, updatedAt: now)))
        startAssessmentWatchdog(callID: current.invite.callID)
    }

    /// The one place a call stops. Reaching it twice is harmless: a server teardown reports
    /// both the caller leaving and the room disconnecting, and the second finds no call.
    @discardableResult
    private func closeCall() -> LiveCall? {
        guard let closed = call else { return nil }
        call = nil
        assessmentWatchdog?.cancel(); assessmentWatchdog = nil
        closed.prepare.cancel()
        // CallKit sends didDeactivate only for a call whose audio it activated, so force the engine off.
        liveKitAudioQueue.async { try? AudioManager.shared.setEngineAvailability(.none) }
        callTeardown = Task { @MainActor [weak self] in
            _ = await closed.prepare.result // join() has finished and cannot create a Room now.
            if let room = closed.room { await room.disconnect() }
            self?.connectLobbyIfNeeded()
        }
        return closed
    }

    private func callEnded(_ reason: String) {
        guard let closed = closeCall() else { return }
        callshieldLog("ended: \(reason)")
        onEvent?(.ended(closed.invite.callID, closed.connected ? .completed : .missed, Date()))
    }

    /// `message` is shown to the person on the call; `detail` is for the log only.
    private func callFailed(_ message: String, detail: String) {
        guard let closed = closeCall() else { return }
        callshieldLog("failed: \(message) (\(detail))")
        onEvent?(.failed(closed.invite.callID, message))
    }

    private func participantLeft(_ identity: String, in room: Room) {
        guard let current = call, current.room === room, current.invite.callerIdentity == identity else { return }
        callshieldLog("caller left")
        callEnded("the caller hung up")
    }

    private func roomDropped(_ room: Room, type: LiveKitErrorType, detail: String) {
        if room === lobbyRoom {
            lobbyRoom = nil
            callshieldLog("lobby dropped: \(detail)")
            // Two phones sharing the lobby token would otherwise keep pushing each other out.
            if type != .duplicateIdentity { scheduleLobbyRetry() }
            return
        }
        guard let current = call, current.room === room else { return }
        switch type {
        // The server closed it: the agent deleted the room, this phone was removed, or a reason
        // the SDK does not map (it reports "room closed" as unknown).
        case .roomDeleted, .participantRemoved, .serverShutdown, .duplicateIdentity, .unknown:
            callEnded("the call room closed (\(detail))")
        default:
            callFailed("The call was interrupted.", detail: detail)
        }
    }

    private func roomReconnected(_ room: Room) {
        guard let current = call, current.room === room else { return }
        let invite = current.invite
        Task { @MainActor in
            guard await self.callerHasLeft(invite, from: room) else { return }
            callshieldLog("caller left while this phone was reconnecting")
            self.callEnded("the caller hung up")
        }
    }

    // MARK: - Voice detector

    private func receiveAssessment(_ data: Data, in room: Room, isAgent: Bool) {
        guard var current = call, current.room === room, current.connected,
              room.connectionState == .connected,
              let update = DeepfakeUpdate.decode(data),
              let assessment = current.detector.receive(update, room: current.invite.room,
                  callerIdentity: current.invite.callerIdentity, isAgent: isAgent, at: Date()) else { return }
        call = current
        onEvent?(.deepfakeAssessment(current.invite.callID, assessment))
    }

    private func startAssessmentWatchdog(callID: UUID) {
        assessmentWatchdog?.cancel()
        assessmentWatchdog = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                do { try await Task.sleep(nanoseconds: 2_000_000_000) } catch { return }
                guard let self, var current = self.call, current.invite.callID == callID,
                      let connectedAt = current.connectedAt else { return }
                if let expired = current.detector.expire(at: Date(), connectedAt: connectedAt) {
                    self.call = current
                    self.onEvent?(.deepfakeAssessment(callID, expired))
                }
            }
        }
    }

    private func assessmentInterrupted(in room: Room) {
        guard let current = call, current.room === room, current.connected else { return }
        onEvent?(.deepfakeAssessment(current.invite.callID, DeepfakeAssessment(state: .unavailable, updatedAt: Date())))
    }

    // MARK: - RoomDelegate
    // Every requirement is `@objc optional`: a label that differs from the protocol compiles and
    // then never fires. The SDK calls these on its own queue, not the main one.

    nonisolated func room(_ room: Room, participant: RemoteParticipant?, didReceiveData data: Data,
                          forTopic topic: String, encryptionType: EncryptionType) { // RoomDelegate.swift:185
        if topic == IncomingCallInvite.topic {
            Task { @MainActor in self.receiveInvite(data, in: room) }
        } else if topic == DeepfakeUpdate.topic {
            // Participant kind is server-authenticated. SIP callers and ordinary clients
            // must never be able to supply their own voice verdicts.
            let isAgent = participant?.kind == .agent
            Task { @MainActor in self.receiveAssessment(data, in: room, isAgent: isAgent) }
        }
    }

    nonisolated func room(_ room: Room, participantDidDisconnect participant: RemoteParticipant) { // RoomDelegate.swift:102
        // Read now: the SDK wipes the participant as soon as this returns. It also sends this for
        // everyone while this phone disconnects or fully reconnects, which is not a hang-up.
        guard let identity = participant.identity?.stringValue, room.connectionState == .connected else { return }
        let isAgent = participant.kind == .agent
        Task { @MainActor in
            if isAgent { self.assessmentInterrupted(in: room) }
            self.participantLeft(identity, in: room)
        }
    }

    nonisolated func room(_ room: Room, didDisconnectWithError error: LiveKitError?) { // RoomDelegate.swift:78
        guard let error else { return } // nil is this phone's own disconnect().
        let type = error.type
        let detail = callshieldDetail(error)
        Task { @MainActor in self.roomDropped(room, type: type, detail: detail) }
    }

    nonisolated func room(_ room: Room, didStartReconnectWithMode reconnectMode: ReconnectMode) {
        Task { @MainActor in self.assessmentInterrupted(in: room) }
    }

    // Unlike roomDidReconnect, this also fires for a quick reconnect, which never leaves `.connected`.
    nonisolated func room(_ room: Room, didCompleteReconnectWithMode reconnectMode: ReconnectMode) { // RoomDelegate.swift:66
        // It fires when a reconnect fails too (Room+Engine.swift cleanUp), and then the room is
        // already disconnected: didDisconnectWithError handles that.
        guard room.connectionState == .connected else { return }
        Task { @MainActor in self.roomReconnected(room) }
    }
}
