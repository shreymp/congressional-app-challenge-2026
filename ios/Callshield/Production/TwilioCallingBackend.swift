import AVFAudio
import Foundation
@preconcurrency import TwilioVoice

/// Account credentials and TwiML live on Shrey's server. This adapter owns only
/// the SDK's calls and short-lived access tokens. Analysis remains on the phone.
@MainActor
final class TwilioCallingBackend: NSObject, CallingBackend, CallDelegate, NotificationDelegate {
    let client: CallingServiceClient
    var isConfigured: Bool { true }
    var onEvent: ((CallingEvent) -> Void)?
    var onIncoming: ((UUID, String, @escaping () -> Void) -> Void)?
    private let audio = DefaultAudioDevice()
    private var calls: [UUID: Call] = [:]
    private var invites: [UUID: CallInvite] = [:]
    private var directions: [UUID: CallDirection] = [:]
    private var analysisTasks: [UUID: Task<Void, Never>] = [:]
    private var pendingPush: (() -> Void)?
    private var registeredToken: Data?
    private var epoch = UUID()
    init(client: CallingServiceClient) {
        self.client = client
        super.init()
        audio.isEnabled = false
        TwilioVoiceSDK.audioDevice = audio
    }
    func start(callID: UUID, number: String) async throws {
        let generation = epoch
        let token: CallingServiceClient.Token = try await client.post("voice/token", body: [:])
        guard generation == epoch else { throw CallingServiceError.cancelled }
        guard !token.token.isEmpty, !token.identity.isEmpty else { throw CallingServiceError.invalidResponse }
        let options = ConnectOptions(accessToken: token.token) { builder in
            builder.uuid = callID
            builder.params = ["To": number]
        }
        directions[callID] = .outgoing
        calls[callID] = TwilioVoiceSDK.connect(options: options, delegate: self)
    }
    func prepareIncoming(callID: UUID, number: String) async throws {
        guard invites[callID] != nil else { throw PhoneError.actionUnavailable }
    }
    func answer(callID: UUID) async throws {
        guard let invite = invites.removeValue(forKey: callID) else { throw PhoneError.actionUnavailable }
        let options = AcceptOptions(callInvite: invite) { $0.uuid = callID }
        directions[callID] = .incoming
        calls[callID] = invite.accept(options: options, delegate: self)
    }
    func end(callID: UUID) async throws {
        analysisTasks.removeValue(forKey: callID)?.cancel()
        invites.removeValue(forKey: callID)?.reject()
        calls.removeValue(forKey: callID)?.disconnect()
        directions.removeValue(forKey: callID)
        epoch = UUID() // Also cancels a token request still preparing this single call.
    }
    private func call(_ id: UUID) throws -> Call {
        guard let call = calls[id] else { throw PhoneError.actionUnavailable }; return call
    }
    func setMuted(_ muted: Bool, callID: UUID) async throws { try call(callID).isMuted = muted }
    func setHeld(_ held: Bool, callID: UUID) async throws {
        try call(callID).isOnHold = held
        if !held { audio.isEnabled = true }
    }
    func sendDTMF(_ digits: String, callID: UUID) async throws { try call(callID).sendDigits(digits) }
    func activateAudio(_ session: AVAudioSession) { audio.isEnabled = true }
    func deactivateAudio(_ session: AVAudioSession) { audio.isEnabled = false }
    func reset() {
        epoch = UUID()
        for work in analysisTasks.values { work.cancel() }; analysisTasks.removeAll()
        let oldCalls = calls; calls.removeAll()
        let oldInvites = invites; invites.removeAll(); directions.removeAll()
        for call in oldCalls.values { call.disconnect() }
        for invite in oldInvites.values { invite.reject() }
        audio.isEnabled = false
    }
    func registerVoIPToken(_ token: Data?) async throws {
        let access: CallingServiceClient.Token = try await client.post("voice/token", body: [:])
        if let token {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                TwilioVoiceSDK.register(accessToken: access.token, deviceToken: token) { error in
                    if let error { continuation.resume(throwing: error) } else { continuation.resume() }
                }
            }
            registeredToken = token
        } else if let old = registeredToken {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                TwilioVoiceSDK.unregister(accessToken: access.token, deviceToken: old) { error in
                    if let error { continuation.resume(throwing: error) } else { continuation.resume() }
                }
            }
            registeredToken = nil
        }
    }
    func handleVoIPPush(_ payload: [AnyHashable: Any], reportIncoming: @escaping (UUID, String, @escaping () -> Void) -> Void,
                       completion: @escaping () -> Void) -> Bool {
        onIncoming = reportIncoming
        pendingPush?(); pendingPush = completion
        let handled = TwilioVoiceSDK.handleNotification(payload, delegate: self, delegateQueue: .main)
        if !handled { pendingPush = nil; onIncoming?(UUID(), "Unknown", completion) }
        return true
    }
    nonisolated func callInviteReceived(callInvite: CallInvite) {
        Task { @MainActor in
            let completion = self.pendingPush ?? {}; self.pendingPush = nil
            self.invites[callInvite.uuid] = callInvite
            self.onIncoming?(callInvite.uuid, callInvite.from ?? "Unknown", completion)
        }
    }
    nonisolated func cancelledCallInviteReceived(cancelledCallInvite: CancelledCallInvite, error: Error) {
        Task { @MainActor in
            if let entry = self.invites.first(where: { $0.value.callSid == cancelledCallInvite.callSid }) {
                self.invites.removeValue(forKey: entry.key)
                self.onEvent?(.ended(entry.key, .missed, Date()))
            }
            self.pendingPush?(); self.pendingPush = nil
        }
    }
    nonisolated func callDidConnect(call: Call) {
        Task { @MainActor in
            guard let id = call.uuid, self.calls[id] === call else { return }
            self.onEvent?(.connected(id, Date()))
            self.analysisTasks[id] = Task { [weak self] in
                guard let self else { return }
                do {
                    let subscription: CallingServiceClient.Subscription = try await self.client.post("voice/analysis", body: [
                        "call_sid": call.sid, "call_uuid": id.uuidString,
                        "direction": self.directions[id]?.rawValue ?? "incoming"])
                    guard !Task.isCancelled, self.calls[id] === call else { return }
                    self.onEvent?(.callerStream(id, subscription.configuration))
                } catch {
                    guard !Task.isCancelled, self.calls[id] === call else { return }
                    self.onEvent?(.analysisFailed(id, error.localizedDescription))
                }
            }
        }
    }
    nonisolated func callDidFailToConnect(call: Call, error: Error) { complete(call, error: error) }
    nonisolated func callDidDisconnect(call: Call, error: Error?) { complete(call, error: error) }
    private nonisolated func complete(_ call: Call, error: Error?) {
        Task { @MainActor in
            guard let id = call.uuid, self.calls[id] === call else { return }
            self.calls.removeValue(forKey: id); self.directions.removeValue(forKey: id)
            self.analysisTasks.removeValue(forKey: id)?.cancel()
            if let error { self.onEvent?(.failed(id, error.localizedDescription)) }
            else { self.onEvent?(.ended(id, .completed, Date())) }
        }
    }
}
