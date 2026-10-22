import Combine
import Foundation
import LiveCommunicationKit

@MainActor
final class ProductionStore: ObservableObject {
    @Published var tab: PhoneTab = .recents
    @Published var filter: CallFilter = .all
    @Published var search = ""
    @Published var contactSearch = ""
    @Published var dialedNumber = ""
    @Published var detail: Person?
    @Published var recordDetail: PhoneCallRecord?
    @Published var showVoicemail = false
    @Published var errorMessage: String?
    @Published var largeText = false { didSet { persist() } }
    @Published private(set) var history: [PhoneCallRecord] = []
    @Published private(set) var contacts: [Person] = []
    @Published private(set) var favorites: [Person] = []
    @Published private(set) var contactsAccess: ContactsAccess = .notRequested
    @Published private(set) var loadingContacts = false
    @Published private(set) var active: PhoneCall?
    @Published private(set) var placingCall = false
    @Published private(set) var voicemail: [VoicemailMessage] = []
    @Published private(set) var loadingVoicemail = false
    @Published var voicemailError: String?
    @Published private(set) var safety = SafetySnapshot()
    @Published private(set) var sharedBlocks: [ServerBlock] = []
    @Published var safetyStatus: String?
    @Published private(set) var syncingSafety = false
    let safetyBackend: SafetyBackend
    private let safetyRepository: SafetyRepository
    private var canPersistSafety = true
    let voicemailBackend: VoicemailBackend
    let coordinator: PhoneCallCoordinator
    let systemPhone: SystemPhoneService
    private let repository: PhoneRepository
    private let contactsService: PhoneContactsService
    private var contactEpoch = 0
    private var hiddenHistoryIDs = Set<UUID>()
    private var canPersist = true
    private var readyToPersist = false
    private var historyObserver: NSObjectProtocol?

    init(repository: PhoneRepository = LocalPhoneRepository(), contactsService: PhoneContactsService = DeviceContactsService(),
         systemPhone: SystemPhoneService? = nil, backend: CallingBackend? = nil, voicemailBackend: VoicemailBackend? = nil,
         safetyRepository: SafetyRepository? = nil, safetyBackend: SafetyBackend? = nil) {
        self.repository = repository
        self.contactsService = contactsService
        self.systemPhone = systemPhone ?? AppleSystemPhoneService()
        self.safetyRepository = safetyRepository ?? (repository is MemoryPhoneRepository ? MemorySafetyRepository() : LocalSafetyRepository())
        self.safetyBackend = safetyBackend ?? HTTPSafetyBackend.configured()
        coordinator = PhoneCallCoordinator(backend: backend ?? AppServices.makeCallingBackend())
        self.voicemailBackend = voicemailBackend ?? AppServices.makeVoicemailBackend()
        do { safety = try self.safetyRepository.load() }
        catch { canPersistSafety = false; safetyStatus = "Your guardians and blocked numbers couldn’t be loaded. Existing saved data has been preserved." }
        do {
            let snapshot = try repository.load()
            history = snapshot.history
            favorites = snapshot.favorites
            largeText = snapshot.largeText
            hiddenHistoryIDs = snapshot.hiddenHistoryIDs
        } catch {
            canPersist = false
            errorMessage = "Your saved call information couldn’t be loaded. \(error.localizedDescription)"
        }
        coordinator.onCallChanged = { [weak self] call in
            var resolved = call
            if let call, let contact = self?.contacts.first(where: { PhoneNumber.matches($0.number, call.person.number) }) {
                resolved?.person = contact
            }
            self?.active = resolved
            if call != nil { self?.detail = nil; self?.recordDetail = nil; self?.showVoicemail = false }
            else { self?.tab = .recents }
        }
        coordinator.onRecord = { [weak self] record in self?.mergeHistory([record]) }
        coordinator.onError = { [weak self] message in self?.errorMessage = message }
        coordinator.shouldBlockIncoming = { [weak self] number in self?.isBlocked(number) ?? false }
        if #available(iOS 26, *), AppConfiguration.defaultDialerEnabled {
            historyObserver = NotificationCenter.default.addObserver(
                forName: ConversationHistoryManager.ConversationHistoryDidUpdate.name, object: nil, queue: .main
            ) { [weak self] _ in Task { @MainActor in await self?.refreshHistory() } }
        }
        readyToPersist = true
    }

    deinit { if let historyObserver { NotificationCenter.default.removeObserver(historyObserver) } }

    #if DEBUG
    /// Fixture used only by the explicit UI-test launch path; never a live assessment.
    func showAnalysisTestCall() {
        let arguments = ProcessInfo.processInfo.arguments
        guard arguments.contains("--ui-test-production"), arguments.contains("--ui-test-analysis") else { return }
        let now = Date()
        let voiceWarning = arguments.contains("--ui-test-voice-warning")
        let transcriptWarning = arguments.contains("--ui-test-transcript-warning")
        let lowScores = arguments.contains("--ui-test-low-scores")
        let voice: DeepfakeAssessment.State = voiceWarning ? .ai : lowScores ? .uncertain : .human
        let transcriptScore = transcriptWarning ? 0.75 : (voiceWarning || lowScores) ? 0.74 : 0.94
        active = PhoneCall(id: UUID(), person: PhoneNumber.person("+15555550100", name: "Analysis test"),
            direction: .incoming, createdAt: now, connectedAt: now, stage: .connected,
            voice: voiceWarning ? .ai : lowScores ? .unknown : .human,
            deepfake: DeepfakeAssessment(state: voice, updatedAt: now, windows: 3,
                                        aiScore: voiceWarning ? 0.75 : lowScores ? 0.74 : 0.12),
            transcript: TranscriptAssessment(state: .monitoring, updatedAt: now, probability: transcriptScore, scoredRevision: 8))
    }
    #endif

    var visibleHistory: [PhoneCallRecord] {
        let query = search.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return history.filter {
            (filter == .all || $0.outcome == .missed) &&
            (query.isEmpty || "\($0.person.name) \($0.person.number) \($0.voice.label)".lowercased().contains(query))
        }
    }
    var visibleContacts: [Person] {
        let query = contactSearch.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return contacts.filter { query.isEmpty || "\($0.name) \($0.number)".lowercased().contains(query) }
    }
    var guardians: [TrustedGuardian] { safety.guardians }
    var blockedNumbers: [ManualBlock] { safety.blocks.filter { !$0.removalPending } }

    func addGuardian(name: String, number: String) throws {
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { throw SafetyError.noName }
        let number = try SafetyNumber.canonical(number)
        if let index = safety.guardians.firstIndex(where: { SafetyNumber.matches($0.number, number) }) {
            safety.guardians[index].name = String(name.prefix(100))
        } else { safety.guardians.append(TrustedGuardian(name: String(name.prefix(100)), number: number)) }
        persistSafety()
    }
    func removeGuardian(_ guardian: TrustedGuardian) {
        safety.guardians.removeAll { $0.id == guardian.id }; persistSafety()
    }
    func isGuardian(_ person: Person) -> Bool { guardians.contains { SafetyNumber.matches($0.number, person.number) } }
    func isBlocked(_ number: String) -> Bool {
        blockedNumbers.contains { SafetyNumber.matches($0.number, number) }
            || sharedBlocks.contains { SafetyNumber.matches($0.number, number) }
    }
    func blockAfterCall(_ person: Person, report: Bool) async {
        guard active == nil else { safetyStatus = "End the call before blocking this number."; return }
        guard !syncingSafety else { safetyStatus = "Wait for the current blocking or reporting change to finish."; return }
        syncingSafety = true
        defer { syncingSafety = false }
        do {
            let number = try SafetyNumber.canonical(person.number)
            if let index = safety.blocks.firstIndex(where: { $0.number == number }) {
                safety.blocks[index].removalPending = false
                safety.blocks[index].serverSynced = false
                safety.blocks[index].reportPending = report
            } else { safety.blocks.append(ManualBlock(number: number, name: person.name, reportPending: report)) }
            persistSafety()
            guard safetyBackend.isConfigured else {
                safetyStatus = "This number is blocked in this app on this iPhone. Server sync" + (report ? " and your report are pending." : " is pending.")
                return
            }
            try await safetyBackend.block(number: number, report: report)
            if let index = safety.blocks.firstIndex(where: { $0.number == number }) {
                safety.blocks[index].serverSynced = true; safety.blocks[index].reportPending = false
            }
            persistSafety()
            safetyStatus = report ? "Number blocked for your callma. calls. Your report is awaiting review for the shared blocklist." : "Number blocked for your callma. calls."
        } catch { safetyStatus = error.localizedDescription }
    }
    func unblock(_ block: ManualBlock) async {
        guard !syncingSafety else { safetyStatus = "Wait for the current blocking or reporting change to finish."; return }
        syncingSafety = true
        defer { syncingSafety = false }
        do {
            if block.serverSynced {
                try await safetyBackend.unblock(number: block.number)
            }
            safety.blocks.removeAll { $0.number == block.number }
            persistSafety()
            safetyStatus = "Personal block removed. A reviewed community block may still apply."
        } catch { safetyStatus = "The server block is still active. " + error.localizedDescription }
    }
    func reportAfterCall(_ person: Person) async {
        guard active == nil else { safetyStatus = "End the call before reporting this number."; return }
        guard !syncingSafety else { safetyStatus = "Wait for the current blocking or reporting change to finish."; return }
        syncingSafety = true
        defer { syncingSafety = false }
        do {
            try await safetyBackend.report(number: SafetyNumber.canonical(person.number), category: "scam")
            safetyStatus = "Report submitted for review. It does not automatically block anyone."
        } catch { safetyStatus = error.localizedDescription }
    }
    func refreshSafety() async {
        guard safetyBackend.isConfigured, !syncingSafety else { return }
        syncingSafety = true
        defer { syncingSafety = false }
        do {
            // Retry explicit manual changes only. Detection scores never enter this path.
            for block in safety.blocks where !block.serverSynced {
                try await safetyBackend.block(number: block.number, report: block.reportPending)
                if let index = safety.blocks.firstIndex(where: { $0.number == block.number }) {
                    safety.blocks[index].serverSynced = true; safety.blocks[index].reportPending = false
                }
            }
            let remote = try await safetyBackend.blocks()
            sharedBlocks = remote.filter { $0.scope == "shared" }
            for block in remote where block.scope == "personal" && !safety.blocks.contains(where: { $0.number == block.number }) {
                safety.blocks.append(ManualBlock(number: block.number, name: block.number, serverSynced: true))
            }
            persistSafety()
        } catch { safetyStatus = "Blocked numbers couldn’t sync. " + error.localizedDescription }
    }
    private func persistSafety() {
        guard canPersistSafety else { safetyStatus = "These changes are temporary because saved safety settings couldn’t be loaded."; return }
        do { try safetyRepository.save(safety) }
        catch { safetyStatus = "Your safety settings couldn’t be saved. " + error.localizedDescription }
    }

    func refresh() async {
        coordinator.registerIncomingCallsIfConfigured()
        await refreshContacts()
        await refreshHistory()
        await refreshSafety()
    }
    func refreshHistory() async {
        do { mergeHistory(try await systemPhone.recentCalls()) }
        catch { errorMessage = "Recent calls couldn’t be refreshed. \(error.localizedDescription)" }
    }

    func allowContacts() async {
        do { _ = try await contactsService.requestAccess(); await refreshContacts() }
        catch { errorMessage = "Contacts couldn’t be opened. \(error.localizedDescription)" }
    }
    func refreshContacts() async {
        contactEpoch += 1
        let epoch = contactEpoch
        contactsAccess = contactsService.access
        guard contactsAccess == .available || contactsAccess == .limited else {
            contacts = []; loadingContacts = false; return
        }
        loadingContacts = true
        do {
            let people = try await contactsService.fetch()
            guard contactEpoch == epoch else { return }
            contactsAccess = contactsService.access
            contacts = contactsAccess == .available || contactsAccess == .limited ? people : []
            if var call = active, let contact = contacts.first(where: { PhoneNumber.matches($0.number, call.person.number) }) {
                call.person = contact
                active = call
            }
            let existingHistory = history
            mergeHistory(existingHistory)
            favorites = favorites.map { favorite in
                contacts.first(where: { PhoneNumber.matches($0.number, favorite.number) }) ?? favorite
            }
            persist()
        } catch {
            guard contactEpoch == epoch else { return }
            contacts = []
            errorMessage = "Contacts couldn’t be loaded. \(error.localizedDescription)"
        }
        loadingContacts = false
    }

    func receive(_ url: URL) {
        do { dialedNumber = try PhoneNumber.fromURL(url); tab = .keypad; detail = nil; recordDetail = nil }
        catch { errorMessage = error.localizedDescription }
        // An external tel: link never places a call without a subsequent Call tap.
    }

    func receiveNumber(_ number: String) {
        do { dialedNumber = try PhoneNumber.normalized(number); tab = .keypad }
        catch { errorMessage = error.localizedDescription }
    }

    func refreshVoicemail() async {
        guard voicemailBackend.isConfigured, !loadingVoicemail else { return }
        loadingVoicemail = true
        voicemailError = nil
        defer { loadingVoicemail = false }
        do { voicemail = try await voicemailBackend.messages().sorted { $0.date > $1.date } }
        catch { voicemailError = error.localizedDescription }
    }
    func markVoicemailRead(_ message: VoicemailMessage) async throws {
        guard !message.isRead, voicemail.first(where: { $0.id == message.id })?.isRead != true else { return }
        try await voicemailBackend.markRead(id: message.id)
        if let index = voicemail.firstIndex(where: { $0.id == message.id }) {
            voicemail[index] = VoicemailMessage(id: message.id, caller: message.caller, date: message.date,
                duration: message.duration, isRead: true, audioURL: message.audioURL)
        }
    }
    func deleteVoicemail(_ message: VoicemailMessage) async {
        do {
            try await voicemailBackend.delete(id: message.id)
            voicemail.removeAll { $0.id == message.id }
        } catch { voicemailError = error.localizedDescription }
    }

    func call(_ person: Person? = nil) async {
        guard !placingCall, active == nil else { return }
        placingCall = true
        defer { placingCall = false }
        do {
            let number = try PhoneNumber.normalized(person?.number ?? dialedNumber)
            let resolved = person ?? contacts.first(where: { PhoneNumber.matches($0.number, number) }) ?? PhoneNumber.person(number)
            // An inbound-only calling service leaves outgoing calls to the mobile service.
            if coordinator.backend.isConfigured && coordinator.backend.canPlaceOutgoingCalls { try await coordinator.start(resolved) }
            else { try await systemPhone.dial(number) }
            // A system handoff is not evidence that a call connected. Its history comes
            // from the entitled system history API, not an invented local duration.
        } catch { errorMessage = error.localizedDescription }
    }

    func toggleFavorite(_ person: Person) {
        if let index = favorites.firstIndex(where: { $0.id == person.id }) { favorites.remove(at: index) }
        else { favorites.append(person) }
        persist()
    }
    func isFavorite(_ person: Person) -> Bool { favorites.contains(where: { $0.id == person.id }) }

    func mergeHistory(_ entries: [PhoneCallRecord]) {
        guard !entries.isEmpty else { return }
        var merged = Dictionary(history.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        for entry in entries {
            guard !hiddenHistoryIDs.contains(entry.id) else { continue }
            // Preserve an app assessment if a later system row has only Unknown.
            let prior = merged[entry.id]
            let person = contacts.first(where: { PhoneNumber.matches($0.number, entry.person.number) }) ?? entry.person
            merged[entry.id] = PhoneCallRecord(id: entry.id, person: person, date: entry.date,
                duration: entry.duration, direction: entry.direction, outcome: entry.outcome,
                voice: entry.deepfake != nil ? entry.voice : (entry.voice == .unknown ? (prior?.voice ?? .unknown) : entry.voice),
                deepfake: entry.deepfake ?? prior?.deepfake,
                transcript: entry.transcript ?? prior?.transcript)
        }
        history = Array(merged.values.sorted { $0.date > $1.date }.prefix(1000))
        persist()
    }
    func removeHistory(_ ids: Set<UUID>) {
        history.removeAll { ids.contains($0.id) }
        hiddenHistoryIDs.formUnion(ids)
        persist()
    }

    private func persist() {
        guard canPersist, readyToPersist else { return }
        do { try repository.save(PhoneSnapshot(history: history, favorites: favorites, largeText: largeText, hiddenHistoryIDs: hiddenHistoryIDs)) }
        catch { errorMessage = "Your changes couldn’t be saved. \(error.localizedDescription)" }
    }
}

/// Tests use this repository so opening the production UI never touches real saved data.
final class MemoryPhoneRepository: PhoneRepository {
    var snapshot = PhoneSnapshot()
    func load() throws -> PhoneSnapshot { snapshot }
    func save(_ snapshot: PhoneSnapshot) throws { self.snapshot = snapshot }
}

