import XCTest

final class ProductionUITests: XCTestCase {
    private var app: XCUIApplication!
    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication(); app.launchArguments = ["--ui-test-production"]; app.launch()
    }
    private func selectTab(_ title: String) {
        let tab = app.tabBars.buttons[title]
        XCTAssertTrue(tab.waitForExistence(timeout: 3))
        tab.tap()
    }
    private func reveal(_ element: XCUIElement) {
        for _ in 0..<5 {
            if element.isHittable { return }
            app.scrollViews.firstMatch.swipeUp()
        }
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
        selectTab("Favorites")
        XCTAssertTrue(app.staticTexts["No favorites"].exists)
        snapshot("Production-02-Favorites")
        selectTab("Contacts")
        XCTAssertFalse(app.staticTexts["Daniel Chen"].exists)
        snapshot("Production-03-Contacts")
        selectTab("Settings")
        XCTAssertTrue(app.staticTexts["callma."].exists)
        XCTAssertTrue(app.staticTexts["call with more peace of mind."].exists)
        // LabeledContent exposes its title and value together to accessibility.
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "Mobile Service")).firstMatch.exists)
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "Unavailable")).firstMatch.exists)
        snapshot("Production-04-Settings")
        selectTab("Recents")
        app.buttons["voicemailButton"].tap()
        XCTAssertTrue(app.staticTexts["Voicemail unavailable"].waitForExistence(timeout: 3))
        snapshot("Production-05-Voicemail")
        app.buttons["Done"].tap()
        XCTAssertTrue(app.tabBars.buttons["Recents"].exists)
    }
    func testBothPipelineResultsAreVisibleOnTheCallScreen() {
        app.terminate()
        app.launchArguments = ["--ui-test-production", "--ui-test-analysis"]
        app.launch()
        XCTAssertTrue(app.buttons["voiceDetailsButton"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["transcriptDetailsButton"].isHittable)
        XCTAssertFalse(app.scrollViews.firstMatch.exists)
        let callerFrame = app.staticTexts["callCallerName"].frame
        let endFrame = app.buttons["End call"].frame
        snapshot("Production-12-Fixed-Call")
        app.buttons["transcriptDetailsButton"].tap()
        XCTAssertTrue(app.staticTexts["transcriptAssessmentTitle"].waitForExistence(timeout: 3))
        XCTAssertEqual(app.staticTexts["transcriptAssessmentTitle"].label, "Possible scam language")
        XCTAssertTrue(app.staticTexts["transcriptAssessmentScore"].label.contains("94 out of 100"))
        XCTAssertTrue(app.staticTexts["transcriptAssessmentScore"].label.contains("experimental"))
        XCTAssertEqual(app.staticTexts["callCallerName"].frame, callerFrame)
        XCTAssertEqual(app.buttons["End call"].frame, endFrame)
        let popover = app.otherElements["callDetailPopover"]
        XCTAssertTrue(popover.waitForExistence(timeout: 3))
        XCTAssertFalse(popover.frame.contains(CGPoint(x: endFrame.midX, y: endFrame.midY)))
        XCTAssertTrue(app.buttons["End call"].isHittable)
        XCTAssertFalse(app.staticTexts["transcriptAssessmentScore"].label.contains("update"))
        snapshot("Production-12-Both-Pipeline-Feedback")
        app.buttons["closeCallDetails"].tap()
        XCTAssertFalse(app.scrollViews.firstMatch.exists)
        app.buttons["voiceDetailsButton"].tap()
        XCTAssertTrue(app.staticTexts["Caller’s voice"].waitForExistence(timeout: 3))
        app.staticTexts["callCallerName"].tap()
        XCTAssertFalse(app.scrollViews.firstMatch.exists)
        XCTAssertTrue(app.buttons["End call"].isHittable)
    }
    func testKeypadAndSimulatorCallError() {
        selectTab("Keypad")
        snapshot("Production-06-Keypad")
        for digit in ["1", "2", "3", "4"] { app.buttons["dialKey\(digit)"].tap() }
        XCTAssertEqual(app.textFields["productionNumber"].value as? String, "1234")
        app.buttons["deleteDigit"].tap()
        XCTAssertEqual(app.textFields["productionNumber"].value as? String, "123")
        app.buttons["productionCallButton"].tap()
        XCTAssertTrue(app.alerts["callma."].waitForExistence(timeout: 3))
        XCTAssertTrue(app.staticTexts["Phone calls require an iPhone. They aren’t available in the simulator."].exists)
        snapshot("Production-07-Simulator-Call")
        app.alerts.buttons["OK"].tap()
        selectTab("Recents")
        XCTAssertTrue(app.staticTexts["No recent calls"].exists)
    }
    func testSafetyStepsOpenAReviewedGuardianDraftWithoutSending() {
        app.terminate()
        app.launchArguments = ["--ui-test-production", "--ui-test-analysis"]
        app.launch()
        let guardian = app.buttons["alertGuardianButton"]
        XCTAssertTrue(guardian.waitForExistence(timeout: 5))
        XCTAssertTrue(guardian.isHittable)
        XCTAssertFalse(app.scrollViews.firstMatch.exists)
        XCTAssertTrue(app.buttons["End call"].isHittable)
        snapshot("Production-13-Safety-Steps")
        guardian.tap()
        XCTAssertTrue(app.navigationBars["Contact a Guardian"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.staticTexts["guardianMessagePreview"].exists)
        snapshot("Production-14-Guardian-Draft")
        app.buttons["Add a Guardian"].tap()
        XCTAssertTrue(app.textFields["guardianName"].waitForExistence(timeout: 3))
        XCTAssertFalse(app.buttons["saveGuardian"].isEnabled)
        app.buttons["Cancel"].tap()
        app.buttons["Done"].tap()
        XCTAssertTrue(app.buttons["End call"].isHittable)
    }

    func testHighSignalReminderAppearsOnceOnReturn() {
        app.terminate()
        app.launchArguments = ["--ui-test-production", "--ui-test-analysis"]
        app.launch()
        XCTAssertTrue(app.buttons["End call"].waitForExistence(timeout: 5))
        XCUIDevice.shared.press(.home)
        app.activate()
        let reminder = app.alerts["Pause Before Sharing"]
        XCTAssertTrue(reminder.waitForExistence(timeout: 5))
        snapshot("Production-15-Return-Reminder")
        reminder.buttons["Continue Call"].tap()
        XCTAssertTrue(reminder.waitForNonExistence(timeout: 3))
        XCUIDevice.shared.press(.home)
        app.activate()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 3))
        XCTAssertFalse(reminder.exists)
        let reachable = NSPredicate(format: "hittable == true")
        expectation(for: reachable, evaluatedWith: app.buttons["End call"])
        waitForExpectations(timeout: 3)
    }

    func testLargestSystemTextKeepsCallControlsReachable() {
        app.terminate()
        app.launchArguments = ["--ui-test-production", "--ui-test-analysis",
                               "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        XCTAssertTrue(app.buttons["End call"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["End call"].isHittable)
        XCTAssertFalse(app.scrollViews.firstMatch.exists)
        XCTAssertTrue(app.buttons["voiceDetailsButton"].isHittable)
        XCTAssertTrue(app.buttons["transcriptDetailsButton"].isHittable)
        snapshot("Production-16-Accessibility-Fixed-Call")
        app.buttons["transcriptDetailsButton"].tap()
        reveal(app.staticTexts["transcriptAssessmentTitle"])
        XCTAssertTrue(app.staticTexts["transcriptAssessmentTitle"].isHittable)
        let endFrame = app.buttons["End call"].frame
        XCTAssertFalse(app.otherElements["callDetailPopover"].frame.contains(CGPoint(x: endFrame.midX, y: endFrame.midY)))
        XCTAssertTrue(app.buttons["End call"].isHittable)
        snapshot("Production-16-Accessibility-Text")
        app.buttons["closeCallDetails"].tap()
        XCTAssertTrue(app.buttons["End call"].isHittable)
        XCTAssertFalse(app.scrollViews.firstMatch.exists)
    }

    func testEitherIndependentScoreCanRevealSafetyStepsAtThreshold() {
        for flag in ["--ui-test-voice-warning", "--ui-test-transcript-warning"] {
            app.terminate()
            app.launchArguments = ["--ui-test-production", "--ui-test-analysis", flag]
            app.launch()
            XCTAssertTrue(app.buttons["alertGuardianButton"].waitForExistence(timeout: 5), flag)
            XCTAssertTrue(app.buttons["End call"].isHittable)
        }
    }

    func testScoresBelowThresholdDoNotShowSafetySteps() {
        app.terminate()
        app.launchArguments = ["--ui-test-production", "--ui-test-analysis", "--ui-test-low-scores"]
        app.launch()
        XCTAssertTrue(app.buttons["End call"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["alertGuardianButton"].exists)
        snapshot("Production-17-Below-Warning-Threshold")
    }

}

