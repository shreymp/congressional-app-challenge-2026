import XCTest

final class ProductionUITests: XCTestCase {
    private var app: XCUIApplication!
    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication(); app.launchArguments = ["--ui-test-production"]; app.launch()
    }
    private func selectTab(_ title: String) {
        let tab = app.buttons["productionTab\(title)"]
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
        XCTAssertTrue(app.staticTexts["Mobile service"].exists)
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "Unavailable")).firstMatch.exists)
        snapshot("Production-04-Settings")
        selectTab("Recents")
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
        let title = app.staticTexts["transcriptAssessmentTitle"]
        XCTAssertTrue(title.waitForExistence(timeout: 5))
        XCTAssertTrue(title.isHittable)
        XCTAssertEqual(title.label, "Scam language")
        XCTAssertEqual(app.staticTexts["transcriptAssessmentScore"].label, "94%")
        XCTAssertEqual(app.staticTexts["deepfakeAssessmentTitle"].label, "Sounds human")
        XCTAssertTrue(app.descendants(matching: .any)["callVerdictHeadline"].label.hasPrefix("Likely scam"))
        snapshot("Restored-Call-Pipeline-Feedback")
        XCTAssertTrue(app.buttons["End call"].isHittable)
    }

    func testRunningChecksShowTheCheckingState() {
        app.terminate()
        app.launchArguments = ["--ui-test-production", "--ui-test-analysis", "--ui-test-analysis-checking"]
        app.launch()
        let headline = app.descendants(matching: .any)["callVerdictHeadline"]
        XCTAssertTrue(headline.waitForExistence(timeout: 5))
        XCTAssertTrue(headline.label.hasPrefix("Checking this call"))
        XCTAssertEqual(app.staticTexts["deepfakeAssessmentTitle"].label, "Checking…")
        XCTAssertEqual(app.staticTexts["transcriptAssessmentTitle"].label, "Listening…")
        XCTAssertFalse(app.buttons["alertGuardianButton"].exists)
        snapshot("Production-21-Checks-Running")
    }
    func testInitialDeadlineShowsInconclusiveWithoutInventingScore() {
        app.terminate()
        app.launchArguments = ["--ui-test-production", "--ui-test-analysis", "--ui-test-analysis-deadline"]
        app.launch()
        XCTAssertTrue(app.staticTexts["deepfakeAssessmentTitle"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["deepfakeAssessmentTitle"].label, "Not sure yet")
        XCTAssertEqual(app.staticTexts["deepfakeAssessmentScore"].label, "No score")
        snapshot("Production-13-Initial-Verdict-Deadline")
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
        snapshot("Restored-Call-Safety-Steps")
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
    }

    func testLargestSystemTextKeepsCallControlsReachable() {
        app.terminate()
        app.launchArguments = ["--ui-test-production", "--ui-test-analysis",
                               "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        XCTAssertTrue(app.buttons["End call"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["End call"].isHittable)
        XCTAssertTrue(app.descendants(matching: .any)["callVerdictHeadline"].isHittable)
        XCTAssertEqual(app.scrollViews.count, 0)
        snapshot("Restored-Accessibility-Call-Controls")
    }

    func testEitherIndependentScoreCanRevealSafetyStepsAtThreshold() {
        for flag in ["--ui-test-voice-warning", "--ui-test-transcript-warning"] {
            app.terminate()
            app.launchArguments = ["--ui-test-production", "--ui-test-analysis", flag]
            app.launch()
            XCTAssertTrue(app.buttons["alertGuardianButton"].waitForExistence(timeout: 5), flag)
            XCTAssertTrue(app.buttons["alertGuardianButton"].isHittable)
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

    func testRestoredContactsAndSettingsKeepSafetyEntryPoints() {
        selectTab("Contacts")
        let add = app.buttons["addTrustedGuardian"]
        XCTAssertTrue(add.waitForExistence(timeout: 3))
        add.tap()
        XCTAssertTrue(app.textFields["guardianName"].waitForExistence(timeout: 3))
        XCTAssertFalse(app.buttons["saveGuardian"].isEnabled)
        app.buttons["Cancel"].tap()
        snapshot("Restored-Contacts-Guardians")
        selectTab("Settings")
        let blocked = app.buttons["blockedNumbersButton"]
        reveal(blocked)
        blocked.tap()
        XCTAssertTrue(app.navigationBars["Blocked Numbers"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.staticTexts["No blocked numbers"].exists)
        snapshot("Restored-Blocked-Numbers")
        app.buttons["Done"].tap()
        XCTAssertTrue(app.buttons["productionTabSettings"].exists)
    }

}
