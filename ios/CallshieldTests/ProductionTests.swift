import AVFAudio
import XCTest
import SwiftUI
@testable import Callshield

@MainActor
final class ProductionTests: XCTestCase {
    private let start = Date(timeIntervalSince1970: 1_800_000_000)
    private var person: Person { PhoneNumber.person("+13125550123", name: "Test Contact") }
    private func record(id: UUID = UUID(), seconds: Int = 0, missed: Bool = false, voice: Voice = .unknown) -> PhoneCallRecord {
        PhoneCallRecord(id: id, person: person, date: start.addingTimeInterval(Double(seconds)), duration: seconds,
                        direction: .incoming, outcome: missed ? .missed : .completed, voice: voice)
    }

    #if targetEnvironment(simulator)
    func testSimulatorIncomingAnswerMuteAndEndUsesBackendWithoutCallKit() async throws {
        let backend = TestInboundBackend()
        let coordinator = PhoneCallCoordinator(backend: backend, microphonePermission: { true })
        let id = UUID()
        var records: [PhoneCallRecord] = []
        coordinator.onRecord = { records.append($0) }
        backend.onEvent?(.incoming(id, "+13125550123", "Simulator caller"))
        XCTAssertEqual(coordinator.active?.stage, .incoming)
        XCTAssertNil(coordinator.active?.connectedAt)
        try await coordinator.answer()
        XCTAssertEqual(backend.answered, [id])
        XCTAssertEqual(backend.activations, 1)
        // A completed answer request alone is not a connected event.
        XCTAssertNil(coordinator.active?.connectedAt)
        backend.onEvent?(.connected(id, Date()))
        XCTAssertEqual(coordinator.active?.stage, .connected)
        try await coordinator.setMuted(true)
        XCTAssertEqual(backend.mutes, [true])
        XCTAssertEqual(coordinator.active?.muted, true)
        try await coordinator.end()
        XCTAssertNil(coordinator.active)
        XCTAssertEqual(backend.ended, [id])
        XCTAssertEqual(records.count, 1)
        XCTAssertEqual(records.first?.outcome, .completed)
        backend.onEvent?(.connected(id, Date()))
        XCTAssertNil(coordinator.active)
    }

    func testSimulatorMicrophoneDenialEndsCallWithoutPublishing() async {
        let backend = TestInboundBackend()
        let coordinator = PhoneCallCoordinator(backend: backend, microphonePermission: { false })
        backend.onEvent?(.incoming(UUID(), "+13125550123", nil))
        do { try await coordinator.answer(); XCTFail("Expected microphone denial") }
        catch { XCTAssertTrue(backend.answered.isEmpty) }
        XCTAssertNil(coordinator.active)
        XCTAssertEqual(backend.activations, 0)
    }

    func testSimulatorDeclineDoesNotActivateAudio() async throws {
        let backend = TestInboundBackend()
        let coordinator = PhoneCallCoordinator(backend: backend)
        var records: [PhoneCallRecord] = []
        coordinator.onRecord = { records.append($0) }
        let id = UUID()
        backend.onEvent?(.incoming(id, "", nil))
        try await coordinator.end()
        XCTAssertEqual(backend.ended, [id])
        XCTAssertTrue(backend.answered.isEmpty)
        XCTAssertEqual(backend.activations, 0)
        XCTAssertEqual(records.first?.outcome, .missed)
    }
    #endif

    func testProductionStartsWithoutSamplesOrCallingService() {
        let store = ProductionStore(repository: MemoryPhoneRepository(), contactsService: TestContacts())
        XCTAssertTrue(store.history.isEmpty)
        XCTAssertTrue(store.contacts.isEmpty)
        XCTAssertTrue(store.favorites.isEmpty)
        XCTAssertNil(store.active)
        XCTAssertFalse(store.coordinator.backend.isConfigured)
        XCTAssertFalse(store.voicemailBackend.isConfigured)
    }
    func testInboundOnlyBackendListensAndLeavesOutgoingCallsToSystemPhone() async {
        let phone = TestSystemPhone(); let backend = TestInboundBackend()
        let store = ProductionStore(repository: MemoryPhoneRepository(), contactsService: TestContacts(), systemPhone: phone, backend: backend)
        XCTAssertEqual(backend.listens, 0)
        await store.refresh()
        XCTAssertEqual(backend.listens, 1)
        await store.call(person)
        XCTAssertEqual(phone.dialed, [person.number])
        XCTAssertNil(store.active)
        XCTAssertNil(store.errorMessage)
    }
    func testBackendThatCannotListenAnymoreIsShownToThePerson() {
        let backend = TestInboundBackend()
        let store = ProductionStore(repository: MemoryPhoneRepository(), contactsService: TestContacts(), backend: backend)
        XCTAssertNil(store.errorMessage)
        backend.onEvent?(.incomingCallsUnavailable("Incoming calls are off."))
        XCTAssertEqual(store.errorMessage, "Incoming calls are off.")
        XCTAssertNil(store.active)
    }
    func testIncomingInviteDecodingAcceptsMissingHandleAndRejectsIncompletePayloads() throws {
        let id = UUID()
        let complete: [String: Any] = ["type": "incoming_call", "callUUID": id.uuidString.lowercased(), "room": "call-test",
                                       "token": "test-token", "handle": "+13125550123", "callerIdentity": "sip_+13125550123",
                                       "callerName": " Test Caller "]
        func decode(_ object: Any) throws -> IncomingCallInvite? {
            let data = try JSONSerialization.data(withJSONObject: object)
            return IncomingCallInvite.decode(data)
        }
        let invite = try XCTUnwrap(try decode(complete))
        XCTAssertEqual(invite, IncomingCallInvite(callID: id, room: "call-test", token: "test-token", handle: "+13125550123",
                                                  callerIdentity: "sip_+13125550123", callerName: "Test Caller"))
        for key in ["handle", "callerName"] {
            var payload = complete; payload[key] = nil
            let partial = try XCTUnwrap(try decode(payload), key)
            XCTAssertEqual(partial.callID, id)
            XCTAssertEqual(key == "handle" ? partial.handle : partial.callerName ?? "", "")
        }
        for key in ["type", "callUUID", "room", "token", "callerIdentity"] {
            var missing = complete; missing[key] = nil
            XCTAssertNil(try decode(missing), key)
            var empty = complete; empty[key] = ""
            XCTAssertNil(try decode(empty), key)
        }
        var notUUID = complete; notUUID["callUUID"] = "not-a-uuid"
        XCTAssertNil(try decode(notUUID))
        var otherType = complete; otherType["type"] = "something_else"
        XCTAssertNil(try decode(otherType))
        XCTAssertNil(try decode([complete]))
        XCTAssertNil(IncomingCallInvite.decode(Data("not json".utf8)))
    }
    func testContactsMatchUSCountryCodeAndRefreshSavedNames() async {
        XCTAssertTrue(PhoneNumber.matches("(312) 555-0123", "+13125550123"))
        XCTAssertFalse(PhoneNumber.matches("", ""))
        XCTAssertFalse(PhoneNumber.matches("+443125550123", "+13125550123"))
        let service = TestContacts(); service.access = .available
        service.people = [PhoneNumber.person("3125550123", name: "Updated Name")]
        let store = ProductionStore(repository: MemoryPhoneRepository(), contactsService: service)
        store.mergeHistory([record()])
        store.toggleFavorite(person)
        await store.refreshContacts()
        XCTAssertEqual(store.history.first?.person.name, "Updated Name")
        XCTAssertEqual(store.favorites.first?.name, "Updated Name")
    }

    func testNumberNormalizationAndRejection() throws {
        XCTAssertEqual(try PhoneNumber.normalized("+1 (312) 555-0123"), "+13125550123")
        XCTAssertEqual(try PhoneNumber.normalized("*123#"), "*123#")
        for value in ["", "+", "++123", "12+3", "tel:123", "123;https://example.com", "１２３", "123\n", String(repeating: "1", count: 65)] {
            XCTAssertThrowsError(try PhoneNumber.normalized(value), value)
        }
    }
    func testExternalURLsPrefillWithoutCalling() async throws {
        let phone = TestSystemPhone()
        let store = ProductionStore(repository: MemoryPhoneRepository(), contactsService: TestContacts(), systemPhone: phone)
        store.receive(try XCTUnwrap(URL(string: "tel:+1%20(312)%20555-0123")))
        XCTAssertEqual(store.dialedNumber, "+13125550123")
        XCTAssertEqual(store.tab, .keypad)
        XCTAssertTrue(phone.dialed.isEmpty)
        XCTAssertTrue(store.history.isEmpty)
        for address in ["https://example.com", "tel://123", "tel:123?next=456", "tel:123#fragment", "tel:123;evil"] {
            XCTAssertThrowsError(try PhoneNumber.fromURL(try XCTUnwrap(URL(string: address))))
        }
    }
    func testExplicitCallUsesSystemPhoneWithoutInventedHistory() async {
        let phone = TestSystemPhone()
        let store = ProductionStore(repository: MemoryPhoneRepository(), contactsService: TestContacts(), systemPhone: phone)
        store.dialedNumber = "+1 (312) 555-0123"
        await store.call()
        XCTAssertEqual(phone.dialed, [person.number])
        XCTAssertNil(store.active)
        XCTAssertTrue(store.history.isEmpty)
        XCTAssertFalse(store.placingCall)
        XCTAssertNil(store.errorMessage)
    }
    func testInvalidNumberNeverReachesSystemService() async {
        let phone = TestSystemPhone()
        let store = ProductionStore(repository: MemoryPhoneRepository(), contactsService: TestContacts(), systemPhone: phone)
        store.dialedNumber = "not a phone number"
        await store.call()
        XCTAssertTrue(phone.dialed.isEmpty)
        XCTAssertNotNil(store.errorMessage)
        XCTAssertFalse(store.placingCall)
    }
    func testSystemCallFailureDoesNotCreateFakeCall() async {
        let phone = TestSystemPhone(); phone.failure = PhoneError.simulatorUnavailable
        let store = ProductionStore(repository: MemoryPhoneRepository(), contactsService: TestContacts(), systemPhone: phone)
        await store.call(person)
        XCTAssertNotNil(store.errorMessage)
        XCTAssertTrue(store.history.isEmpty)
        XCTAssertNil(store.active)
    }
    func testContactsRequirePermissionAndClearWhenRevoked() async {
        let service = TestContacts(); service.people = [person]
        let store = ProductionStore(repository: MemoryPhoneRepository(), contactsService: service)
        await store.refreshContacts()
        XCTAssertEqual(service.fetchCount, 0)
        await store.allowContacts()
        XCTAssertEqual(service.requests, 1)
        XCTAssertEqual(store.contacts, [person])
        store.contactSearch = " TEST "
        XCTAssertEqual(store.visibleContacts, [person])
        store.contactSearch = "no result"
        XCTAssertTrue(store.visibleContacts.isEmpty)
        service.access = .denied
        await store.refreshContacts()
        XCTAssertTrue(store.contacts.isEmpty)
        XCTAssertFalse(store.loadingContacts)
    }
    func testLimitedContactsAndFetchFailure() async {
        let service = TestContacts(); service.access = .limited; service.people = [person]
        let store = ProductionStore(repository: MemoryPhoneRepository(), contactsService: service)
        await store.refreshContacts()
        XCTAssertEqual(store.contactsAccess, .limited)
        XCTAssertEqual(store.contacts, [person])
        service.failure = PhoneError.actionUnavailable
        await store.refreshContacts()
        XCTAssertTrue(store.contacts.isEmpty)
        XCTAssertNotNil(store.errorMessage)
        XCTAssertFalse(store.loadingContacts)
    }
    func testHistoryMergeFiltersAndDeletedRowsStayDeletedAfterRefreshAndRelaunch() async {
        let repository = MemoryPhoneRepository()
        let phone = TestSystemPhone()
        let store = ProductionStore(repository: repository, contactsService: TestContacts(), systemPhone: phone)
        let id = UUID(); let checked = record(id: id, seconds: 10, voice: .human)
        store.mergeHistory([checked, record(missed: true)])
        phone.records = [record(id: id, seconds: 10)]
        await store.refreshHistory()
        XCTAssertEqual(store.history.count, 2)
        XCTAssertEqual(store.history[0].voice, .human)
        store.filter = .missed
        XCTAssertEqual(store.visibleHistory.count, 1)
        store.filter = .all; store.search = "likely human"
        XCTAssertEqual(store.visibleHistory, [checked])
        store.removeHistory([id])
        await store.refreshHistory()
        XCTAssertEqual(store.history.count, 1)
        let restored = ProductionStore(repository: repository, contactsService: TestContacts(), systemPhone: phone)
        await restored.refreshHistory()
        XCTAssertEqual(restored.history.count, 1)
        XCTAssertTrue(repository.snapshot.hiddenHistoryIDs.contains(id))
    }
    func testFavoritesAndPreferencePersistWithoutDemoData() {
        let repository = MemoryPhoneRepository()
        let store = ProductionStore(repository: repository, contactsService: TestContacts())
        store.toggleFavorite(person); store.largeText = true
        let restored = ProductionStore(repository: repository, contactsService: TestContacts())
        XCTAssertEqual(restored.favorites, [person]); XCTAssertTrue(restored.largeText)
        restored.toggleFavorite(person)
        XCTAssertFalse(restored.isFavorite(person))
        XCTAssertTrue(repository.snapshot.favorites.isEmpty)
    }
    func testCorruptRepositoryIsNotOverwrittenAndWriteErrorsAreVisible() {
        let repository = FailingRepository(); repository.failLoad = true
        let store = ProductionStore(repository: repository, contactsService: TestContacts())
        XCTAssertNotNil(store.errorMessage)
        store.toggleFavorite(person)
        XCTAssertEqual(repository.writes, 0)
        repository.failLoad = false
        let writable = ProductionStore(repository: repository, contactsService: TestContacts())
        writable.toggleFavorite(person)
        XCTAssertEqual(repository.writes, 1); XCTAssertNotNil(writable.errorMessage)
    }
    func testLocalFileRoundTripAndHistoryBound() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let repository = LocalPhoneRepository(url: directory.appendingPathComponent("phone.json"))
        XCTAssertTrue(try repository.load().history.isEmpty)
        let history = (0..<1001).map { record(seconds: $0) }
        try repository.save(PhoneSnapshot(history: history, favorites: [person], largeText: true, hiddenHistoryIDs: [history[0].id]))
        let loaded = try repository.load()
        XCTAssertEqual(loaded.history.count, 1000)
        XCTAssertEqual(loaded.favorites, [person]); XCTAssertTrue(loaded.largeText)
        XCTAssertTrue(loaded.hiddenHistoryIDs.contains(history[0].id))
    }
    func testSessionOnlyRealConnectionStartsClockAndAssessment() {
        var state = PhoneSessionState(); let id = UUID()
        XCTAssertTrue(state.begin(PhoneCall(id: id, person: person, direction: .incoming, createdAt: start, stage: .incoming)))
        state.assess(id: id, voice: .ai)
        XCTAssertEqual(state.current?.voice, .unknown)
        state.connecting(id: id)
        XCTAssertEqual(state.current?.stage, .connecting)
        XCTAssertNil(state.current?.connectedAt)
        state.connected(id: id, at: start.addingTimeInterval(10))
        state.assess(id: id, voice: .human)
        let ended = state.finish(id: id, outcome: .completed, at: start.addingTimeInterval(75))
        XCTAssertEqual(ended?.duration, 65); XCTAssertEqual(ended?.voice, .human)
        XCTAssertNil(state.finish(id: id, outcome: .completed, at: start.addingTimeInterval(76)))
    }
    func testSessionIgnoresStaleEventsAndDuplicateConnections() {
        var state = PhoneSessionState(); let old = UUID(); let id = UUID()
        _ = state.begin(PhoneCall(id: id, person: person, direction: .outgoing, createdAt: start, stage: .connecting))
        state.connected(id: old, at: start); state.assess(id: old, voice: .ai)
        XCTAssertNil(state.current?.connectedAt); XCTAssertEqual(state.current?.voice, .unknown)
        state.connected(id: id, at: start); state.setHeld(true, id: id)
        state.connected(id: id, at: start.addingTimeInterval(100))
        XCTAssertEqual(state.current?.connectedAt, start); XCTAssertEqual(state.current?.stage, .held)
        state.setMuted(true, id: old); state.setSpeaker(true, id: old)
        XCTAssertFalse(state.current!.muted); XCTAssertFalse(state.current!.speaker)
        XCTAssertNil(state.finish(id: old, outcome: .failed, at: start))
        XCTAssertEqual(state.current?.id, id)
    }
    func testUnansweredAndUnfinishedAssessmentSaveUnknown() {
        for connected in [false, true] {
            var state = PhoneSessionState(); let id = UUID()
            _ = state.begin(PhoneCall(id: id, person: person, direction: .incoming, createdAt: start, stage: .incoming))
            if connected { state.connected(id: id, at: start); state.assess(id: id, voice: .analyzing) }
            let ended = state.finish(id: id, outcome: connected ? .completed : .missed, at: start.addingTimeInterval(4))
            XCTAssertEqual(ended?.voice, .unknown); XCTAssertEqual(ended?.duration, connected ? 4 : 0)
            _ = state.begin(PhoneCall(id: UUID(), person: person, direction: .outgoing, createdAt: start, stage: .connecting))
            state.assess(id: id, voice: .ai)
            XCTAssertEqual(state.current?.voice, .unknown)
        }
    }
    func testVoicemailServiceStateAndActionsWaitForBackend() async throws {
        let backend = TestVoicemail()
        let store = ProductionStore(repository: MemoryPhoneRepository(), contactsService: TestContacts(), voicemailBackend: backend)
        let message = VoicemailMessage(id: "vm1", caller: person, date: start, duration: 20, isRead: false, audioURL: URL(string: "https://example.com/voice")!)
        backend.items = [message]
        await store.refreshVoicemail()
        XCTAssertEqual(store.voicemail, [message])
        try await store.markVoicemailRead(message)
        try await store.markVoicemailRead(message)
        XCTAssertTrue(store.voicemail[0].isRead); XCTAssertEqual(backend.readIDs, [message.id])
        backend.failure = PhoneError.actionUnavailable
        await store.deleteVoicemail(message)
        XCTAssertEqual(store.voicemail.count, 1); XCTAssertNotNil(store.voicemailError)
        backend.failure = nil
        await store.deleteVoicemail(message)
        XCTAssertTrue(store.voicemail.isEmpty)
    }

    func testRenderProductionCallStatesForVisualReview() async throws {
        let store = ProductionStore(repository: MemoryPhoneRepository(), contactsService: TestContacts())
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.first as? UIWindowScene)
        let previousWindow = scene.windows.first(where: \.isKeyWindow)
        let window = UIWindow(windowScene: scene)
        defer { window.isHidden = true; window.rootViewController = nil; previousWindow?.makeKey() }
        // Review fixtures only: this does not register a call, use a backend, or
        // become part of the app's production launch path.
        for (name, stage, voice) in [
            ("Production-08-Incoming-Fixture", PhoneCall.Stage.incoming, Voice.unknown),
            ("Production-09-Connecting-Fixture", .connecting, .unknown),
            ("Production-10-Connected-Fixture", .connected, .unknown),
            ("Production-11-Assessed-Fixture", .connected, .human)
        ] {
            let call = PhoneCall(id: UUID(), person: person, direction: .incoming, createdAt: Date(),
                connectedAt: stage == .connected ? Date().addingTimeInterval(-65) : nil, stage: stage, voice: voice)
            let controller = UIHostingController(rootView: ProductionCallView(call: call).environmentObject(store)
                .environment(\.colorScheme, .dark))
            window.rootViewController = controller
            window.makeKeyAndVisible()
            try await Task.sleep(nanoseconds: 150_000_000)
            controller.view.layoutIfNeeded()
            let image = UIGraphicsImageRenderer(bounds: controller.view.bounds).image { _ in
                controller.view.drawHierarchy(in: controller.view.bounds, afterScreenUpdates: true)
            }
            let attachment = XCTAttachment(image: image)
            attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
        }
    }
}

private final class TestContacts: PhoneContactsService {
    var access: ContactsAccess = .notRequested
    var people: [Person] = []; var failure: Error?
    var fetchCount = 0; var requests = 0
    func requestAccess() async throws -> Bool { requests += 1; access = .available; return true }
    func fetch() async throws -> [Person] { fetchCount += 1; if let failure { throw failure }; return people }
}
@MainActor private final class TestSystemPhone: SystemPhoneService {
    var dialed: [String] = []; var records: [PhoneCallRecord] = []; var failure: Error?
    func dial(_ number: String) async throws { dialed.append(number); if let failure { throw failure } }
    func recentCalls() async throws -> [PhoneCallRecord] { records }
}
private final class FailingRepository: PhoneRepository {
    var failLoad = false; var writes = 0
    func load() throws -> PhoneSnapshot { if failLoad { throw PhoneError.actionUnavailable }; return PhoneSnapshot() }
    func save(_ snapshot: PhoneSnapshot) throws { writes += 1; throw PhoneError.actionUnavailable }
}
/// Configured, but inbound-only and without PushKit, like the LiveKit backend. Opens no connection.
@MainActor private final class TestInboundBackend: CallingBackend {
    var isConfigured: Bool { true }
    var usesVoIPPush: Bool { false }
    var canPlaceOutgoingCalls: Bool { false }
    var supportsHoldAndKeypad: Bool { false }
    var onEvent: ((CallingEvent) -> Void)?
    var listens = 0
    var answered: [UUID] = []
    var ended: [UUID] = []
    var mutes: [Bool] = []
    var activations = 0
    func listenForIncomingCalls() { listens += 1 }
    func start(callID: UUID, number: String) async throws { throw PhoneError.serviceUnavailable }
    func prepareIncoming(callID: UUID, number: String) async throws {}
    func answer(callID: UUID) async throws { answered.append(callID) }
    func end(callID: UUID) async throws { ended.append(callID) }
    func setMuted(_ muted: Bool, callID: UUID) async throws { mutes.append(muted) }
    func setHeld(_ held: Bool, callID: UUID) async throws {}
    func sendDTMF(_ digits: String, callID: UUID) async throws {}
    func registerVoIPToken(_ token: Data?) async throws {}
    func activateAudio(_ session: AVAudioSession) { activations += 1 }
    func deactivateAudio(_ session: AVAudioSession) {}
    func reset() {}
}
@MainActor private final class TestVoicemail: VoicemailBackend {
    var isConfigured = true; var items: [VoicemailMessage] = []; var readIDs: [String] = []; var failure: Error?
    func messages() async throws -> [VoicemailMessage] { if let failure { throw failure }; return items }
    func markRead(id: String) async throws { if let failure { throw failure }; readIDs.append(id) }
    func delete(id: String) async throws { if let failure { throw failure }; items.removeAll { $0.id == id } }
}

