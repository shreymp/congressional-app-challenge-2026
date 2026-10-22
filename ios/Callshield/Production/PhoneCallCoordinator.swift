import AVFAudio
import CallKit
import Foundation
import PushKit

@MainActor
final class PhoneCallCoordinator: NSObject, CXProviderDelegate, PKPushRegistryDelegate {
    let backend: CallingBackend
    private let microphonePermission: @MainActor () async -> Bool
    private let provider: CXProvider
    private let controller = CXCallController()
    private var registry: PKPushRegistry?
    private var session = PhoneSessionState()
    var onCallChanged: ((PhoneCall?) -> Void)?
    var onRecord: ((PhoneCallRecord) -> Void)?
    var onError: ((String) -> Void)?
    var shouldBlockIncoming: ((String) -> Bool)?
    var active: PhoneCall? { session.current }

    init(backend: CallingBackend, microphonePermission: @escaping @MainActor () async -> Bool = {
        await withCheckedContinuation { continuation in
            AVAudioSession.sharedInstance().requestRecordPermission { continuation.resume(returning: $0) }
        }
    }) {
        self.backend = backend
        self.microphonePermission = microphonePermission
        let configuration = CXProviderConfiguration()
        configuration.supportedHandleTypes = [.phoneNumber, .generic]
        configuration.supportsVideo = false
        configuration.maximumCallGroups = 1
        configuration.maximumCallsPerCallGroup = 1
        configuration.includesCallsInRecents = true
        provider = CXProvider(configuration: configuration)
        super.init()
        provider.setDelegate(self, queue: .main)
        backend.onEvent = { [weak self] event in self?.receive(event) }
    }

    func registerIncomingCallsIfConfigured() {
        guard backend.isConfigured else { return }
        backend.listenForIncomingCalls()
        // PushKit needs the push entitlement. A backend that rings through `incoming` events gets no registry.
        guard backend.usesVoIPPush, registry == nil else { return }
        let registry = PKPushRegistry(queue: .main)
        registry.delegate = self
        registry.desiredPushTypes = [.voIP]
        self.registry = registry
    }

    func start(_ person: Person) async throws {
        guard backend.isConfigured else { throw PhoneError.serviceUnavailable }
        guard active == nil else { throw PhoneError.actionUnavailable }
        let permitted = await microphonePermission()
        guard permitted else { throw PhoneError.microphoneDenied }
        let number = try PhoneNumber.normalized(person.number)
        let call = PhoneCall(id: UUID(), person: person, direction: .outgoing, createdAt: Date(), stage: .connecting)
        guard session.begin(call) else { throw PhoneError.actionUnavailable }
        changed()
        let action = CXStartCallAction(call: call.id, handle: CXHandle(type: .phoneNumber, value: number))
        do { try await request(action) }
        catch { finish(call.id, outcome: .failed, reason: .failed); throw error }
    }

    func answer() async throws {
        guard let call = active, call.stage == .incoming else { throw PhoneError.actionUnavailable }
        try await request(CXAnswerCallAction(call: call.id))
    }
    func end() async throws {
        guard let id = active?.id else { return }
        try await request(CXEndCallAction(call: id))
    }
    func setMuted(_ value: Bool) async throws {
        guard let id = active?.id else { throw PhoneError.actionUnavailable }
        try await request(CXSetMutedCallAction(call: id, muted: value))
    }
    func setHeld(_ value: Bool) async throws {
        guard let id = active?.id, active?.connectedAt != nil else { throw PhoneError.actionUnavailable }
        try await request(CXSetHeldCallAction(call: id, onHold: value))
    }
    func sendDTMF(_ digits: String) async throws {
        guard let id = active?.id, active?.connectedAt != nil, !digits.isEmpty,
              digits.allSatisfy({ "0123456789*#".contains($0) }) else { throw PhoneError.actionUnavailable }
        try await request(CXPlayDTMFCallAction(call: id, digits: digits, type: .singleTone))
    }
    func setSpeaker(_ value: Bool) throws {
        guard let id = active?.id, active?.connectedAt != nil else { throw PhoneError.actionUnavailable }
        try AVAudioSession.sharedInstance().overrideOutputAudioPort(value ? .speaker : .none)
        session.setSpeaker(value, id: id)
        changed()
    }

    private func request(_ action: CXAction) async throws {
        #if targetEnvironment(simulator)
        // Simulator has no system call UI/audio activation. Use the same real backend
        // through the app controls; only physical devices submit CallKit transactions.
        guard let action = action as? CXCallAction, let call = active, call.id == action.callUUID else {
            throw PhoneError.actionUnavailable
        }
        switch action {
        case is CXAnswerCallAction:
            let allowed = await microphonePermission()
            guard active?.id == call.id else { throw PhoneError.actionUnavailable }
            do {
                guard allowed else { throw PhoneError.microphoneDenied }
                session.connecting(id: call.id)
                changed()
                try await backend.answer(callID: call.id)
                guard active?.id == call.id else { return }
                backend.activateAudio(AVAudioSession.sharedInstance())
            } catch {
                guard active?.id == call.id else { throw error }
                backend.reset()
                finish(call.id, outcome: .failed, reason: .failed)
                throw error
            }
        case is CXEndCallAction:
            do { try await backend.end(callID: call.id) }
            catch { backend.reset(); finish(call.id, outcome: .failed, reason: .failed); throw error }
            finish(call.id, outcome: call.connectedAt == nil ? (call.direction == .incoming ? .missed : .cancelled) : .completed,
                   reason: .remoteEnded)
        case let mute as CXSetMutedCallAction:
            try await backend.setMuted(mute.isMuted, callID: call.id)
            guard active?.id == call.id else { return }
            session.setMuted(mute.isMuted, id: call.id)
            changed()
        default: throw PhoneError.actionUnavailable
        }
        #else
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            controller.request(CXTransaction(action: action)) { error in
                if let error { continuation.resume(throwing: error) }
                else { continuation.resume() }
            }
        }
        #endif
    }

    private func changed() { onCallChanged?(active) }
    private func finish(_ id: UUID, outcome: PhoneCallOutcome, reason: CXCallEndedReason, at date: Date = Date()) {
        guard let record = session.finish(id: id, outcome: outcome, at: date) else { return }
        #if targetEnvironment(simulator)
        backend.deactivateAudio(AVAudioSession.sharedInstance())
        #else
        provider.reportCall(with: id, endedAt: date, reason: reason)
        #endif
        changed()
        onRecord?(record)
    }

    private func receive(_ event: CallingEvent) {
        switch event {
        case .connected(let id, let date):
            guard active?.id == id else { return }
            session.connected(id: id, at: date)
            #if !targetEnvironment(simulator)
            if active?.direction == .outgoing { provider.reportOutgoingCall(with: id, connectedAt: date) }
            #endif
            changed()
        case .ended(let id, let outcome, let date):
            finish(id, outcome: outcome, reason: outcome == .missed ? .unanswered : .remoteEnded, at: date)
        case .assessmentStarted(let id): session.assess(id: id, voice: .analyzing); changed()
        case .assessed(let id, let voice):
            guard voice != .analyzing else { return }
            session.assess(id: id, voice: voice); changed()
        case .deepfakeAssessment(let id, let assessment):
            session.assessDeepfake(id: id, assessment: assessment); changed()
        case .transcriptAssessment(let id, let assessment):
            session.assessTranscript(id: id, assessment: assessment); changed()
        case .failed(let id, let message):
            guard active?.id == id else { return }
            backend.reset()
            finish(id, outcome: .failed, reason: .failed)
            onError?(message)
        case .incoming(let id, let handle, let name):
            if shouldBlockIncoming?(handle) == true {
                Task { try? await backend.end(callID: id) }
            } else { reportIncoming(id, handle: handle, name: name) }
        case .incomingCallsUnavailable(let message): onError?(message)
        }
    }

    /// A backend that rings without PushKit announced a call while the app is open.
    private func reportIncoming(_ id: UUID, handle: String, name: String?) {
        // `end` for a call that never rang only makes the backend forget it.
        guard active == nil else { Task { @MainActor in try? await self.backend.end(callID: id) }; return }
        let number = try? PhoneNumber.normalized(handle)
        let name = name.map { String($0.prefix(128)) }
        let update = CXCallUpdate()
        // A withheld or non-numeric caller ID still rings, under a neutral label.
        update.remoteHandle = number.map { CXHandle(type: .phoneNumber, value: $0) } ?? CXHandle(type: .generic, value: "Unknown caller")
        update.localizedCallerName = name
        update.supportsHolding = false
        // The call-room token cannot publish data, and the server drops keypad tones without that grant.
        update.supportsDTMF = false
        update.supportsGrouping = false
        update.supportsUngrouping = false
        let person = number.map { PhoneNumber.person($0, name: name) }
            ?? Person(name: name ?? "Unknown caller", number: "", initials: "?", color: .slate, voice: .unknown)
        #if targetEnvironment(simulator)
        guard session.begin(PhoneCall(id: id, person: person, direction: .incoming,
                                     createdAt: Date(), stage: .incoming)) else { return }
        print("[callma.] Simulator incoming call; use Accept in the app")
        changed()
        Task { @MainActor in
            do { try await self.backend.prepareIncoming(callID: id, number: number ?? "") }
            catch {
                guard self.active?.id == id else { return }
                self.backend.reset()
                self.finish(id, outcome: .failed, reason: .failed)
                self.onError?(error.localizedDescription)
            }
        }
        #else
        provider.reportNewIncomingCall(with: id, update: update) { error in
            Task { @MainActor in
                // CallKit can refuse (Do Not Disturb, a blocked caller). Then nothing rang and there is no session.
                if let error {
                    print("[callma.] CallKit refused the incoming call: \(error.localizedDescription)")
                    try? await self.backend.end(callID: id)
                    return
                }
                guard self.session.begin(PhoneCall(id: id, person: person, direction: .incoming,
                                                   createdAt: Date(), stage: .incoming)) else {
                    self.provider.reportCall(with: id, endedAt: Date(), reason: .failed)
                    try? await self.backend.end(callID: id)
                    return
                }
                print("[callma.] CallKit reported the incoming call")
                self.changed()
                Task { @MainActor in
                    do { try await self.backend.prepareIncoming(callID: id, number: number ?? "") }
                    catch {
                        guard self.active?.id == id else { return }
                        self.backend.reset()
                        self.finish(id, outcome: .failed, reason: .failed)
                        self.onError?(error.localizedDescription)
                    }
                }
            }
        }
        #endif
    }

    nonisolated func providerDidReset(_ provider: CXProvider) {
        Task { @MainActor in
            self.backend.reset()
            if let id = self.active?.id { self.finish(id, outcome: .failed, reason: .failed) }
        }
    }

    nonisolated func provider(_ provider: CXProvider, perform action: CXStartCallAction) {
        Task { @MainActor in
            guard self.active?.id == action.callUUID else { action.fail(); return }
            do {
                try AVAudioSession.sharedInstance().setCategory(.playAndRecord, mode: .voiceChat, options: [.allowBluetoothHFP])
                provider.reportOutgoingCall(with: action.callUUID, startedConnectingAt: Date())
                try await self.backend.start(callID: action.callUUID, number: action.handle.value)
                guard self.active?.id == action.callUUID else { action.fail(); return }
                action.fulfill()
                let update = CXCallUpdate()
                update.localizedCallerName = self.active?.person.name
                update.remoteHandle = action.handle
                update.supportsHolding = true
                update.supportsDTMF = true
                update.supportsGrouping = false
                update.supportsUngrouping = false
                provider.reportCall(with: action.callUUID, updated: update)
            } catch {
                action.fail()
                guard self.active?.id == action.callUUID else { return }
                self.backend.reset()
                self.finish(action.callUUID, outcome: .failed, reason: .failed)
                self.onError?(error.localizedDescription)
            }
        }
    }

    nonisolated func provider(_ provider: CXProvider, perform action: CXAnswerCallAction) {
        Task { @MainActor in
            guard self.active?.id == action.callUUID else { action.fail(); return }
            let allowed = await self.microphonePermission()
            guard allowed else {
                action.fail()
                self.backend.reset() // The backend may already have joined the call silently.
                self.finish(action.callUUID, outcome: .failed, reason: .failed)
                self.onError?(PhoneError.microphoneDenied.localizedDescription)
                return
            }
            guard self.active?.id == action.callUUID else { action.fail(); return }
            self.session.connecting(id: action.callUUID)
            self.changed()
            do {
                try AVAudioSession.sharedInstance().setCategory(.playAndRecord, mode: .voiceChat, options: [.allowBluetoothHFP])
                try await self.backend.answer(callID: action.callUUID)
                guard self.active?.id == action.callUUID else { action.fail(); return }
                action.fulfill()
                // The backend's connected event, not answering alone, starts the duration/analysis.
            } catch {
                action.fail()
                guard self.active?.id == action.callUUID else { return }
                self.backend.reset()
                self.finish(action.callUUID, outcome: .failed, reason: .failed)
                self.onError?(error.localizedDescription)
            }
        }
    }

    nonisolated func provider(_ provider: CXProvider, perform action: CXEndCallAction) {
        Task { @MainActor in
            guard let call = self.active, call.id == action.callUUID else { action.fulfill(); return }
            do { try await self.backend.end(callID: action.callUUID) }
            catch { self.backend.reset(); self.onError?(error.localizedDescription) }
            self.finish(action.callUUID, outcome: call.connectedAt == nil ? (call.direction == .incoming ? .missed : .cancelled) : .completed, reason: .remoteEnded)
            action.fulfill()
        }
    }

    nonisolated func provider(_ provider: CXProvider, perform action: CXSetMutedCallAction) {
        Task { @MainActor in
            guard self.active?.id == action.callUUID else { action.fail(); return }
            do {
                try await self.backend.setMuted(action.isMuted, callID: action.callUUID)
                guard self.active?.id == action.callUUID else { action.fail(); return }
                self.session.setMuted(action.isMuted, id: action.callUUID)
                self.changed(); action.fulfill()
            } catch { action.fail(); self.onError?(error.localizedDescription) }
        }
    }
    nonisolated func provider(_ provider: CXProvider, perform action: CXSetHeldCallAction) {
        Task { @MainActor in
            guard self.active?.id == action.callUUID else { action.fail(); return }
            do {
                try await self.backend.setHeld(action.isOnHold, callID: action.callUUID)
                guard self.active?.id == action.callUUID else { action.fail(); return }
                self.session.setHeld(action.isOnHold, id: action.callUUID)
                self.changed(); action.fulfill()
            } catch { action.fail(); self.onError?(error.localizedDescription) }
        }
    }
    nonisolated func provider(_ provider: CXProvider, perform action: CXPlayDTMFCallAction) {
        Task { @MainActor in
            guard self.active?.id == action.callUUID else { action.fail(); return }
            do { try await self.backend.sendDTMF(action.digits, callID: action.callUUID); action.fulfill() }
            catch { action.fail(); self.onError?(error.localizedDescription) }
        }
    }
    nonisolated func provider(_ provider: CXProvider, timedOutPerforming action: CXAction) {
        Task { @MainActor in
            guard let action = action as? CXCallAction, self.active?.id == action.callUUID else { return }
            self.backend.reset()
            self.finish(action.callUUID, outcome: .failed, reason: .failed)
        }
    }
    nonisolated func provider(_ provider: CXProvider, didActivate audioSession: AVAudioSession) {
        Task { @MainActor in self.backend.activateAudio(audioSession) }
    }
    nonisolated func provider(_ provider: CXProvider, didDeactivate audioSession: AVAudioSession) {
        Task { @MainActor in self.backend.deactivateAudio(audioSession) }
    }

    nonisolated func pushRegistry(_ registry: PKPushRegistry, didUpdate pushCredentials: PKPushCredentials, for type: PKPushType) {
        guard type == .voIP else { return }
        Task { @MainActor in
            do { try await self.backend.registerVoIPToken(pushCredentials.token) }
            catch { self.onError?(error.localizedDescription) }
        }
    }
    nonisolated func pushRegistry(_ registry: PKPushRegistry, didInvalidatePushTokenFor type: PKPushType) {
        guard type == .voIP else { return }
        Task { @MainActor in
            do { try await self.backend.registerVoIPToken(nil) }
            catch { self.onError?(error.localizedDescription) }
        }
    }
    nonisolated func pushRegistry(_ registry: PKPushRegistry, didReceiveIncomingPushWith payload: PKPushPayload,
                                 for type: PKPushType, completion: @escaping () -> Void) {
        guard type == .voIP else { completion(); return }
        let dictionary = payload.dictionaryPayload
        let parsedID = (dictionary["callUUID"] as? String).flatMap(UUID.init(uuidString:))
        let number = (dictionary["handle"] as? String).flatMap { try? PhoneNumber.normalized($0) }
        let name = (dictionary["callerName"] as? String).map { String($0.prefix(128)) }
        Task { @MainActor in
            // Report immediately, before any backend work. Even malformed VoIP pushes must
            // satisfy Apple's CallKit reporting obligation, then end the rejected call.
            let id = parsedID ?? UUID()
            let update = CXCallUpdate()
            update.remoteHandle = CXHandle(type: .phoneNumber, value: number ?? "Unknown")
            update.localizedCallerName = name
            update.supportsHolding = true
            update.supportsDTMF = true
            update.supportsGrouping = false
            update.supportsUngrouping = false
            defer { completion() }
            do { try await self.provider.reportNewIncomingCall(with: id, update: update) }
            catch { return }
            guard parsedID != nil, let number, self.backend.isConfigured,
                  self.session.begin(PhoneCall(id: id, person: PhoneNumber.person(number, name: name),
                                              direction: .incoming, createdAt: Date(), stage: .incoming)) else {
                self.provider.reportCall(with: id, endedAt: Date(), reason: .failed)
                return
            }
            self.changed()
            Task { @MainActor in
                do { try await self.backend.prepareIncoming(callID: id, number: number) }
                catch {
                    guard self.active?.id == id else { return }
                    self.backend.reset()
                    self.finish(id, outcome: .failed, reason: .failed)
                    self.onError?(error.localizedDescription)
                }
            }
        }
    }
}


