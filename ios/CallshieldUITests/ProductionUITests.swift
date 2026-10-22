import XCTest

final class ProductionUITests: XCTestCase {
    private var app: XCUIApplication!
    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication(); app.launchArguments = ["--ui-test-production"]; app.launch()
    }
    private func snapshot(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
    func testProductionNavigationWithoutSampleCallers() {
        XCTAssertTrue(app.staticTexts["No recent calls"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["demoButton"].exists)
        XCTAssertFalse(app.staticTexts["Sarah Miller"].exists)
        snapshot("Production-01-Recents")
        app.buttons["productionTabFavorites"].tap()
        XCTAssertTrue(app.staticTexts["No favorites"].exists)
        snapshot("Production-02-Favorites")
        app.buttons["productionTabContacts"].tap()
        XCTAssertFalse(app.staticTexts["Daniel Chen"].exists)
        snapshot("Production-03-Contacts")
        app.buttons["productionTabSettings"].tap()
        XCTAssertTrue(app.staticTexts["Mobile service"].exists)
        XCTAssertTrue(app.staticTexts["Unavailable"].exists)
        snapshot("Production-04-Settings")
        app.buttons["productionTabRecents"].tap()
        app.buttons["voicemailButton"].tap()
        XCTAssertTrue(app.staticTexts["Voicemail unavailable"].waitForExistence(timeout: 3))
        snapshot("Production-05-Voicemail")
        app.buttons["Done"].tap()
        XCTAssertTrue(app.buttons["productionTabRecents"].exists)
    }
    func testBothPipelineResultsAreVisibleOnTheCallScreen() {
        app.terminate()
        app.launchArguments = ["--ui-test-production", "--ui-test-analysis"]
        app.launch()
        XCTAssertTrue(app.staticTexts["Voice check"].waitForExistence(timeout: 5))
        if !app.staticTexts["transcriptAssessmentTitle"].isHittable { app.swipeUp() }
        XCTAssertEqual(app.staticTexts["transcriptAssessmentTitle"].label, "Possible scam language")
        XCTAssertTrue(app.staticTexts["transcriptAssessmentScore"].label.contains("94%"))
        snapshot("Production-12-Both-Pipeline-Feedback")
    }
    func testKeypadAndSimulatorCallError() {
        app.buttons["productionTabKeypad"].tap()
        snapshot("Production-06-Keypad")
        for digit in ["1", "2", "3", "4"] { app.buttons["dialKey\(digit)"].tap() }
        XCTAssertEqual(app.textFields["productionNumber"].value as? String, "1234")
        app.buttons["deleteDigit"].tap()
        XCTAssertEqual(app.textFields["productionNumber"].value as? String, "123")
        app.buttons["productionCallButton"].tap()
        XCTAssertTrue(app.alerts["Callshield"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.staticTexts["Phone calls require an iPhone. They aren’t available in the simulator."].exists)
        snapshot("Production-07-Simulator-Call")
        app.alerts.buttons["OK"].tap()
        app.buttons["productionTabRecents"].tap()
        XCTAssertTrue(app.staticTexts["No recent calls"].exists)
    }
}

