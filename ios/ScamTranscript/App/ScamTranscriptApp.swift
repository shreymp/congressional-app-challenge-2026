import SwiftUI

@main
struct ScamTranscriptApp: App {
    var body: some Scene { WindowGroup { ContentView() } }
}

struct ContentView: View {
    @State private var testText = ""
    @StateObject private var controller = RecordingController()
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Button(controller.buttonTitle) { controller.toggle() }
                    .buttonStyle(.borderedProminent)
                    .tint(controller.state == .recording ? .red : .blue)
                    .disabled(controller.isBusy)
                    .accessibilityIdentifier("recordButton")
                Button("Print last score") { controller.printLastScore() }
                    .buttonStyle(.bordered)
                    .accessibilityIdentifier("printScoreButton")
            }
            Picker("Scorer", selection: Binding(get: { controller.decisionMaker }, set: { controller.selectDecisionMaker($0) })) {
                ForEach(RecordingController.DecisionMaker.allCases, id: \.self) { mode in Text(mode.rawValue).tag(mode) }
            }
            .accessibilityIdentifier("modelPicker")
            DisclosureGroup("Test a typed transcript") {
                TextEditor(text: $testText)
                    .frame(height: 100).border(.secondary)
                    .accessibilityIdentifier("testTranscript")
                HStack {
                    Button("Scam example") { testText = "Caller: Your bank account will be frozen. Tell me the verification code I just sent you immediately. Do not tell anyone." }
                    Button("Dentist example") { testText = "Caller: Hi, this is your dentist calling to confirm your cleaning appointment tomorrow at ten. Please call our usual office number if you need to reschedule." }
                }.font(.caption)
                Button(controller.jevBusy ? "Scoring…" : "Score text") { controller.testTranscript(testText) }
                    .disabled(controller.jevBusy || testText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .accessibilityIdentifier("scoreTextButton")
            }
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(controller.logs) { log in
                            Text(log.text)
                                .font(.system(.caption, design: .monospaced))
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .id(log.id)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .accessibilityIdentifier("logs")
                .onChange(of: controller.logs.last?.id) { _ in
                    if let last = controller.logs.last { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
        }
        .padding()
        .onChange(of: scenePhase) { phase in if phase == .background { controller.stop() } }
    }
}
