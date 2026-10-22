import XCTest

final class CallshieldUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["--ui-test-demo"]
        app.launch()
    }

    private func snapshot(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func beginDemo(_ voice: String) {
        app.buttons["demoButton"].tap()
        XCTAssertTrue(app.buttons["demoCaller-\(voice)"].waitForExistence(timeout: 3))
        app.buttons["demoCaller-\(voice)"].tap()
        XCTAssertTrue(app.buttons["acceptCall"].waitForExistence(timeout: 3))
    }

    func testAllScreensAndNavigation() {
        XCTAssertTrue(app.buttons["callRow-1"].waitForExistence(timeout: 3))
        snapshot("01-Recents")
        app.buttons["callRow-1"].tap()
        XCTAssertTrue(app.staticTexts["02:22"].waitForExistence(timeout: 3))
        snapshot("02-Call-Details")
        app.buttons["sheetDone"].tap()
        app.buttons["tabContacts"].tap()
        XCTAssertTrue(app.buttons["contact-DC"].exists)
        snapshot("03-Contacts")
        app.buttons["contact-DC"].tap()
        XCTAssertTrue(app.staticTexts["Sample contact. Changes stay in this demo session."].waitForExistence(timeout: 3))
        snapshot("04-Contact-Details")
        app.buttons["sheetDone"].tap()
        XCTAssertTrue(app.buttons["contact-DC"].exists)
        app.buttons["tabSettings"].tap()
        XCTAssertTrue(app.staticTexts["callma."].exists)
        XCTAssertTrue(app.staticTexts["call with more peace of mind."].exists)
        XCTAssertFalse(app.staticTexts["UNDERSTANDING VOICE LABELS"].exists)
        snapshot("05-Settings")
        app.switches["largerTextToggle"].tap()
        XCTAssertEqual(app.switches["largerTextToggle"].value as? String, "1")
        app.buttons["demoButton"].tap()
        XCTAssertTrue(app.buttons["demoCaller-human"].waitForExistence(timeout: 3))
        snapshot("06-Demo-Picker")
        app.buttons["sheetDone"].tap()
        XCTAssertTrue(app.switches["largerTextToggle"].exists)
        app.buttons["tabRecents"].tap()
        snapshot("07-Recents-Larger-Text")
    }

    func testDemoKeypadBlocksCallsAndFavoritesWork() {
        app.buttons["tabKeypad"].tap()
        XCTAssertFalse(app.buttons["demoCallButton"].isEnabled)
        for digit in ["1", "2", "3", "4"] { app.buttons["dialKey\(digit)"].tap() }
        XCTAssertEqual(app.textFields["demoNumber"].value as? String, "1234")
        app.buttons["Delete digit"].tap()
        XCTAssertEqual(app.textFields["demoNumber"].value as? String, "123")
        snapshot("14-Demo-Keypad")
        app.buttons["demoCallButton"].tap()
        XCTAssertTrue(app.alerts["Calls unavailable in demo"].waitForExistence(timeout: 3))
        app.alerts.buttons["OK"].tap()
        XCTAssertFalse(app.buttons["endCall"].exists)
        XCTAssertEqual(app.textFields["demoNumber"].value as? String, "123")
        app.buttons["tabFavorites"].tap()
        XCTAssertTrue(app.staticTexts["No favorites"].exists)
        app.buttons["Open Contacts"].tap()
        app.buttons["contact-DC"].tap()
        app.buttons["demoContactCall"].tap()
        XCTAssertTrue(app.alerts["Calls unavailable in demo"].waitForExistence(timeout: 3))
        app.alerts.buttons["OK"].tap()
        app.buttons["demoFavoriteToggle"].tap()
        app.buttons["sheetDone"].tap()
        app.buttons["tabFavorites"].tap()
        XCTAssertTrue(app.buttons["favorite-DC"].exists)
        app.buttons["favorite-DC"].tap()
        app.buttons["demoFavoriteToggle"].tap()
        app.buttons["sheetDone"].tap()
        XCTAssertTrue(app.staticTexts["No favorites"].exists)
    }

    func testVoiceHelpAppearsAtTheResult() {
        beginDemo("human")
        app.buttons["acceptCall"].tap()
        XCTAssertTrue(app.staticTexts["This voice appears to be human."].waitForExistence(timeout: 6))
        app.buttons["About Likely human"].tap()
        XCTAssertTrue(app.staticTexts["The voice appears human. This does not verify the caller or mean the call is safe."].waitForExistence(timeout: 3))
        snapshot("Restored-Demo-Voice-Help")
        app.buttons["Done"].tap()
        XCTAssertTrue(app.buttons["endCall"].exists)
    }

    func testSearchFiltersAndEmptyState() {
        app.buttons["filterMissed"].tap()
        XCTAssertFalse(app.buttons["callRow-1"].exists)
        XCTAssertTrue(app.buttons["callRow-2"].exists)
        app.buttons["filterAll"].tap()
        app.textFields["callSearch"].tap()
        app.textFields["callSearch"].typeText("Likely AI")
        XCTAssertTrue(app.buttons["callRow-4"].exists)
        XCTAssertFalse(app.buttons["callRow-1"].exists)
        app.buttons["Clear search"].tap()
        app.textFields["callSearch"].typeText("no matching caller")
        XCTAssertTrue(app.staticTexts["No calls found"].exists)
        snapshot("08-Empty-Search")
    }

    func testHumanCallControlsAndHistory() {
        beginDemo("human")
        snapshot("09-Incoming-Call")
        XCTAssertFalse(app.otherElements["activeVoiceLabel"].exists)
        XCTAssertFalse(app.scrollViews.firstMatch.exists)
        app.buttons["acceptCall"].tap()
        XCTAssertTrue(app.buttons["endCall"].waitForExistence(timeout: 3))
        XCTAssertFalse(app.scrollViews.firstMatch.exists)
        XCTAssertTrue(app.staticTexts["Checking the simulated voice…"].exists)
        snapshot("10-Analyzing-Call")
        XCTAssertTrue(app.staticTexts["This voice appears to be human."].waitForExistence(timeout: 5))
        app.buttons["muteCall"].tap()
        app.buttons["speakerCall"].tap()
        XCTAssertEqual(app.buttons["muteCall"].value as? String, "On")
        XCTAssertEqual(app.buttons["speakerCall"].value as? String, "On")
        snapshot("11-Active-Human-Call")
        app.buttons["endCall"].tap()
        XCTAssertTrue(app.buttons["tabRecents"].waitForExistence(timeout: 3))
        let firstCall = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'callRow-'")).firstMatch
        XCTAssertTrue(firstCall.label.contains("Sarah Miller, received, Likely human"))
        firstCall.tap()
        XCTAssertTrue(app.staticTexts["Incoming call"].waitForExistence(timeout: 3))
    }

    func testAIAndUncertainCalls() {
        beginDemo("ai")
        app.buttons["acceptCall"].tap()
        XCTAssertTrue(app.staticTexts["This voice may be AI-generated."].waitForExistence(timeout: 6))
        snapshot("12-Active-AI-Call")
        app.buttons["endCall"].tap()
        beginDemo("unknown")
        app.buttons["acceptCall"].tap()
        XCTAssertTrue(app.staticTexts["There isn’t enough information to tell."].waitForExistence(timeout: 6))
        snapshot("13-Active-Uncertain-Call")
        app.buttons["endCall"].tap()
    }

    func testDeclineAndThirtySecondTimeout() {
        beginDemo("ai")
        app.buttons["declineCall"].tap()
        XCTAssertTrue(app.buttons["tabRecents"].waitForExistence(timeout: 3))
        var firstCall = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'callRow-'")).firstMatch
        XCTAssertTrue(firstCall.label.contains("Unknown Caller, missed, Unknown"))
        beginDemo("human")
        XCTAssertTrue(app.buttons["tabRecents"].waitForExistence(timeout: 33))
        firstCall = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'callRow-'")).firstMatch
        XCTAssertTrue(firstCall.label.contains("Sarah Miller, missed, Unknown"))
    }
}
