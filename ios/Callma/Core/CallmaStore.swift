import Combine
import Foundation

/// The TSX demo's state machine. It does not connect to telephony or an AI service.
/// Deadlines belong to the current call, so an ended call cannot classify a later one.
@MainActor
final class CallmaStore: ObservableObject {
    @Published var tab: AppTab = .recents
    @Published var filter: CallFilter = .all
    @Published var search = ""
    @Published var sheet: AppSheet?
    @Published var largeText = false
    @Published var dialedNumber = ""
    @Published var errorMessage: String?
    @Published private(set) var favoriteNumbers: Set<String> = []
    var favorites: [Person] { SampleData.contacts.filter { favoriteNumbers.contains($0.number) } }

    func toggleFavorite(_ person: Person) {
        if favoriteNumbers.contains(person.number) { favoriteNumbers.remove(person.number) }
        else { favoriteNumbers.insert(person.number) }
    }

    func previewOutgoing(_ number: String) {
        guard !number.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        errorMessage = "This is an interactive demo. No call was placed. Use Demo to try a simulated incoming call."
    }
    @Published private(set) var calls = SampleData.history
    @Published private(set) var active: ActiveCall?
    @Published private(set) var muted = false
    @Published private(set) var speaker = false
    @Published private(set) var seconds = 0
    @Published private(set) var notice = ""
    private var noticeDeadline: Date?

    var visibleCalls: [CallEntry] {
        let query = search.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return calls.filter { call in
            (filter == .all || call.missed) &&
            (query.isEmpty || "\(call.person.name) \(call.person.number) \(call.voice.label)".lowercased().contains(query))
        }
    }

    func startCall(_ person: Person, now: Date = Date()) {
        guard active == nil else { return }
        sheet = nil
        muted = false
        speaker = false
        seconds = 0
        notice = ""
        noticeDeadline = nil
        active = ActiveCall(id: UUID(), person: person, stage: .ringing, voice: .unknown, started: now)
    }

    func accept(now: Date = Date()) {
        tick(now: now)
        guard var call = active, call.stage == .ringing else { return }
        call.stage = .connected
        call.voice = .analyzing
        call.started = now
        seconds = 0
        active = call
    }

    func finishCall(now: Date = Date()) {
        tick(now: now)
        guard let call = active else { return }
        save(call, now: now, timedOut: false)
    }

    func toggleMute() {
        guard active?.stage == .connected else { return }
        muted.toggle()
    }

    func toggleSpeaker() {
        guard active?.stage == .connected else { return }
        speaker.toggle()
    }

    /// Also invoked on foregrounding: elapsed time is wall time, not timer ticks.
    func tick(now: Date = Date()) {
        if let deadline = noticeDeadline, now >= deadline {
            notice = ""
            noticeDeadline = nil
        }
        guard var call = active else { return }
        let elapsed = max(0, now.timeIntervalSince(call.started))
        if call.stage == .ringing {
            if elapsed >= 30 { save(call, now: now, timedOut: true) }
            return
        }
        let newSeconds = Int(elapsed)
        if seconds != newSeconds { seconds = newSeconds }
        if call.voice == .analyzing && elapsed >= 2.6 {
            call.voice = call.person.voice
            call.scamRisk = SampleData.scamRisk(for: call.person)
            active = call
        }
    }

    private func save(_ call: ActiveCall, now: Date, timedOut: Bool) {
        let missed = call.stage == .ringing
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US")
        formatter.dateFormat = "h:mm a"
        calls.insert(CallEntry(id: UUID().uuidString, person: call.person,
                               when: formatter.string(from: now), missed: missed,
                               duration: missed ? 0 : max(0, Int(now.timeIntervalSince(call.started))),
                               voice: missed || call.voice == .analyzing ? .unknown : call.voice,
                               scamRisk: missed ? nil : call.scamRisk), at: 0)
        active = nil
        sheet = nil
        tab = .recents
        notice = timedOut ? "Missed demo call added to Recents" :
            missed ? "Declined demo call added to Recents" : "Demo call ended"
        noticeDeadline = now.addingTimeInterval(3.5)
    }
}
