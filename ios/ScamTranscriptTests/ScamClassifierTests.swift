import XCTest
@testable import ScamTranscript

final class ScamClassifierTests: XCTestCase {
    let classifier = ScamClassifier()
    func testExplicitCodeScamSeparatesFromDentist() {
        let scam = classifier.assess("Tell me the verification code right now. Do not tell anyone. Stay on the line.")
        XCTAssertEqual(scam.level, .high)
        XCTAssertEqual(scam.signals.filter { $0.id == "code" }.count, 1)
        XCTAssertEqual(classifier.assess("This is the dentist calling to reschedule your appointment for Tuesday.").level, .clear)
    }
    func testLegitimateSensitiveTopicsDoNotTriggerRequests() {
        for text in [
            "This is your bank. We never ask you to share your verification code.",
            "Do not share your password or verification code with anyone.",
            "Enter the verification code in the official app on your phone.",
            "You can pay your invoice through our website tomorrow.",
            "Please buy a gift card for your sister's birthday.",
            "Please call the number printed on your bank card.",
            "Your appointment is urgent. Please come in right now.",
            "We will not ask you to give us your password.",
            "Never send gift card numbers to a stranger.",
            "I read about verification code scams in the news."
        ] {
            XCTAssertEqual(classifier.assess(text).level, .clear, text)
        }
    }
    func testDifferentHighConcernRequests() {
        for text in [
            "Pay the fine with gift cards immediately. You will be arrested.",
            "Give me your password right now. Stay on the line.",
            "Install AnyDesk immediately. Keep this secret.",
            "Send me the gift card numbers. Do not tell your family.",
            "Give me your social security number. Do not tell anyone. Right now.",
            "Send money using bitcoin immediately. Your account will be closed."
        ] {
            XCTAssertEqual(classifier.assess(text).level, .high, text)
        }
    }
    func testEmptyAndShortSpeechIsInsufficient() {
        XCTAssertEqual(classifier.assess("").level, .insufficient)
        XCTAssertEqual(classifier.assess("hello there").level, .insufficient)
    }
    func testRepeatedPhrasesDoNotInflateScore() {
        let text = "Tell me your verification code."
        XCTAssertEqual(classifier.assess(text).score, classifier.assess(text + " " + text).score)
    }
    func testNegationDoesNotSuppressLaterDemand() {
        let result = classifier.assess("Do not share it with strangers, but tell me your verification code right now. Keep this secret.")
        XCTAssertEqual(result.level, .high)
    }
    func testPartialReplacesRatherThanAccumulates() {
        var window = TranscriptWindow(maxWords: 8)
        window.updatePartial("tell me")
        window.updatePartial("tell me your code")
        XCTAssertEqual(window.text, "tell me your code")
        window.commit("tell me your code")
        XCTAssertEqual(window.text, "tell me your code")
        window.updatePartial("keep this secret right now")
        XCTAssertEqual(window.text.split(separator: " ").count, 8)
        window.commit("keep this secret right now")
        XCTAssertTrue(window.partial.isEmpty)
    }
    func testOldEvidenceFallsOutOfWindow() {
        var window = TranscriptWindow(maxWords: 12)
        window.commit("Tell me your verification code. Keep this secret.")
        XCTAssertEqual(classifier.assess(window.text).level, .high)
        window.commit("We are calling about a routine dental appointment next week on Tuesday morning.")
        XCTAssertEqual(classifier.assess(window.text).level, .clear)
    }
}
