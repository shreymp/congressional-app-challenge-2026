import XCTest
@testable import Callma

@MainActor
final class CallmaStoreTests: XCTestCase {
    private let start = Date(timeIntervalSince1970: 1_800_000_000)

    func testInitialHistoryAndContactsMatchTSX() {
        let store = CallmaStore()
        XCTAssertEqual(store.tab, .recents)
        XCTAssertEqual(store.calls.count, 7)
        XCTAssertEqual(store.calls.filter(\.missed).count, 3)
        XCTAssertEqual(SampleData.contacts.map(\.initials), ["SM", "DC", "AR"])
        XCTAssertEqual(SampleData.demoPeople.map(\.voice), [.human, .ai, .unknown])
    }

    func testSearchNamesNumbersAndLabelsWithMissedFilter() {
        let store = CallmaStore()
        store.search = " SARAH "
        XCTAssertEqual(store.visibleCalls.count, 2)
        store.filter = .missed
        XCTAssertEqual(store.visibleCalls.count, 1)
        store.filter = .all
        store.search = "555-0186"
        XCTAssertEqual(store.visibleCalls.first?.person.name, "Appointment Reminder")
        store.search = "LIKELY HUMAN"
        XCTAssertEqual(store.visibleCalls.count, 3)
        store.filter = .missed
        XCTAssertTrue(store.visibleCalls.isEmpty)
        store.search = "not a caller"
        XCTAssertTrue(store.visibleCalls.isEmpty)
    }

    func testRingingNeverAnalyzesBeforeAcceptance() {
        let store = CallmaStore()
        store.sheet = .demo
        store.startCall(SampleData.people[1], now: start)
        XCTAssertNil(store.sheet)
        store.tick(now: start.addingTimeInterval(29.9))
        XCTAssertEqual(store.active?.stage, .ringing)
        XCTAssertEqual(store.active?.voice, .unknown)
        XCTAssertEqual(store.seconds, 0)
    }

    func testAnalysisDeadlineAndConnectedClock() {
        let store = CallmaStore()
        store.startCall(SampleData.people[1], now: start)
        let accepted = start.addingTimeInterval(10)
        store.accept(now: accepted)
        XCTAssertEqual(store.active?.voice, .analyzing)
        store.tick(now: accepted.addingTimeInterval(2.59))
        XCTAssertEqual(store.active?.voice, .analyzing)
        store.tick(now: accepted.addingTimeInterval(2.6))
        XCTAssertEqual(store.active?.voice, .ai)
        XCTAssertEqual(store.seconds, 2)
        store.tick(now: accepted.addingTimeInterval(65))
        XCTAssertEqual(store.seconds, 65)
    }

    func testAllThreeDemoAssessments() {
        for person in SampleData.demoPeople {
            let store = CallmaStore()
            store.startCall(person, now: start)
            store.accept(now: start)
            store.finishCall(now: start.addingTimeInterval(5))
            XCTAssertEqual(store.calls.first?.voice, person.voice)
            XCTAssertEqual(store.calls.first?.duration, 5)
            XCTAssertEqual(store.calls.first?.missed, false)
            XCTAssertNil(store.active)
        }
    }

    func testEndingBeforeAnalysisSavesUnknownAndDoesNotUpdateLater() {
        let store = CallmaStore()
        store.startCall(SampleData.people[0], now: start)
        store.accept(now: start)
        store.finishCall(now: start.addingTimeInterval(1))
        let entry = store.calls[0]
        XCTAssertEqual(entry.voice, .unknown)
        XCTAssertEqual(entry.duration, 1)
        store.tick(now: start.addingTimeInterval(10))
        XCTAssertEqual(store.calls[0], entry)
    }

    func testDeclineSavesMissedUnknownAndReturnsToRecents() {
        let store = CallmaStore()
        store.tab = .contacts
        store.startCall(SampleData.people[1], now: start)
        store.finishCall(now: start.addingTimeInterval(2))
        XCTAssertEqual(store.calls.first?.missed, true)
        XCTAssertEqual(store.calls.first?.duration, 0)
        XCTAssertEqual(store.calls.first?.voice, .unknown)
        XCTAssertEqual(store.calls.count, 8)
        XCTAssertEqual(store.tab, .recents)
        XCTAssertEqual(store.notice, "Declined demo call added to Recents")
    }

    func testTimeoutIsExactlyThirtySecondsAndOnlySavesOnce() {
        let store = CallmaStore()
        store.startCall(SampleData.people[0], now: start)
        store.tick(now: start.addingTimeInterval(29.99))
        XCTAssertNotNil(store.active)
        store.tick(now: start.addingTimeInterval(30))
        XCTAssertNil(store.active)
        XCTAssertEqual(store.calls.first?.missed, true)
        XCTAssertEqual(store.calls.first?.voice, .unknown)
        XCTAssertEqual(store.notice, "Missed demo call added to Recents")
        store.finishCall(now: start.addingTimeInterval(31))
        store.tick(now: start.addingTimeInterval(32))
        XCTAssertEqual(store.calls.count, 8)
    }

    func testForegroundReconciliationCannotAcceptAnExpiredCall() {
        let store = CallmaStore()
        store.startCall(SampleData.people[0], now: start)
        store.accept(now: start.addingTimeInterval(60))
        XCTAssertNil(store.active)
        XCTAssertEqual(store.calls.first?.missed, true)
    }

    func testOldAnalysisCannotBleedIntoNewCall() {
        let store = CallmaStore()
        store.startCall(SampleData.people[1], now: start)
        store.accept(now: start)
        store.finishCall(now: start.addingTimeInterval(1))
        store.startCall(SampleData.people[0], now: start.addingTimeInterval(2))
        store.tick(now: start.addingTimeInterval(3))
        XCTAssertEqual(store.active?.stage, .ringing)
        XCTAssertEqual(store.active?.voice, .unknown)
        store.accept(now: start.addingTimeInterval(3))
        store.tick(now: start.addingTimeInterval(6))
        XCTAssertEqual(store.active?.voice, .human)
    }

    func testMuteSpeakerAndFreshSessionReset() {
        let store = CallmaStore()
        store.toggleMute()
        XCTAssertFalse(store.muted)
        store.startCall(SampleData.people[0], now: start)
        store.toggleSpeaker()
        XCTAssertFalse(store.speaker)
        store.accept(now: start)
        store.toggleMute()
        store.toggleSpeaker()
        XCTAssertTrue(store.muted)
        XCTAssertTrue(store.speaker)
        store.finishCall(now: start.addingTimeInterval(5))
        store.startCall(SampleData.people[1], now: start.addingTimeInterval(6))
        XCTAssertFalse(store.muted)
        XCTAssertFalse(store.speaker)
        XCTAssertEqual(store.seconds, 0)
    }

    func testStartingDuringActiveCallAndRepeatedAcceptAreIgnored() {
        let store = CallmaStore()
        store.startCall(SampleData.people[0], now: start)
        let id = store.active?.id
        store.startCall(SampleData.people[1], now: start)
        XCTAssertEqual(store.active?.id, id)
        store.accept(now: start)
        store.accept(now: start.addingTimeInterval(10))
        XCTAssertEqual(store.active?.started, start)
    }

    func testNoticeExpiresAndNextCallClearsIt() {
        let store = CallmaStore()
        store.startCall(SampleData.people[0], now: start)
        store.finishCall(now: start)
        store.tick(now: start.addingTimeInterval(3.49))
        XCTAssertFalse(store.notice.isEmpty)
        store.tick(now: start.addingTimeInterval(3.5))
        XCTAssertTrue(store.notice.isEmpty)
        store.startCall(SampleData.people[0], now: start.addingTimeInterval(4))
        store.finishCall(now: start.addingTimeInterval(5))
        store.startCall(SampleData.people[0], now: start.addingTimeInterval(6))
        XCTAssertTrue(store.notice.isEmpty)
    }

    func testDurationFormatting() {
        XCTAssertEqual(callDuration(0), "00:00")
        XCTAssertEqual(callDuration(142), "02:22")
        XCTAssertEqual(callDuration(316), "05:16")
        XCTAssertEqual(callDuration(3600), "60:00")
    }
}
