import XCTest

final class RecordingUITests: XCTestCase {
    @MainActor
    func testTypedTrainedModelFromUI() {
        let app = XCUIApplication()
        app.launch()
        let picker = app.buttons["modelPicker"]
        XCTAssertTrue(picker.waitForExistence(timeout: 10))
        picker.tap()
        app.buttons["Trained Jev v1"].tap()
        app.buttons["Test a typed transcript"].tap()
        app.buttons["Scam example"].tap()
        app.buttons["scoreTextButton"].tap()
        let result = app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Trained Jev v1: experimental scam score'")).firstMatch
        XCTAssertTrue(result.waitForExistence(timeout: 30))
    }

    @MainActor
    func testRecordStopAndRestart() {
        let app = XCUIApplication()
        app.launch()
        let button = app.buttons["recordButton"]
        XCTAssertTrue(button.waitForExistence(timeout: 10))
        XCTAssertEqual(button.label, "Record")
        XCTAssertTrue(app.buttons["modelPicker"].exists)
        let scoreButton = app.buttons["printScoreButton"]
        scoreButton.tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Last score: 0 | Waiting for speech'")).firstMatch.exists)
        for _ in 0..<2 {
            button.tap()
            let recording = NSPredicate(format: "label == 'Stop'")
            expectation(for: recording, evaluatedWith: button)
            waitForExpectations(timeout: 30)
            XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Recording. Audio'")).firstMatch.exists)
            button.tap()
            expectation(for: NSPredicate(format: "label == 'Record'"), evaluatedWith: button)
            waitForExpectations(timeout: 15)
            scoreButton.tap()
            XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Last score:'")).firstMatch.exists)
        }
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Record button and logs"
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
