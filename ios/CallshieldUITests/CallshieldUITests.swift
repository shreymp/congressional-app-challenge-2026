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
        XCTAssertTrue(app.staticTexts["Sample contact for incoming caller identification. Outgoing calls are not available."].waitForExistence(timeout: 3))
        snapshot("04-Contact-Details")
        app.buttons["sheetDone"].tap()
        XCTAssertTrue(app.buttons["contact-DC"].exists)
        app.buttons["tabSettings"].tap()
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
        app.buttons["acceptCall"].tap()
        XCTAssertTrue(app.buttons["endCall"].waitForExistence(timeout: 3))
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
