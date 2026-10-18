import SwiftUI
import UniformTypeIdentifiers

struct TranscriptStatusView: View {
    @ObservedObject var pipeline: TranscriptPipeline
    var compact = false
    @State private var expanded = false
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Transcript protection", systemImage: "text.bubble")
                .font(.headline)
            Text(pipeline.isPaused ? "Paused while on hold" : pipeline.state.rawValue).font(.caption)
                .accessibilityIdentifier("transcriptState")
            if pipeline.scoring { ProgressView("Checking transcript…") }
            if let error = pipeline.error { Text(error).font(.caption).foregroundStyle(.orange) }
            Text(pipeline.text.isEmpty ? "Waiting for caller speech." : pipeline.text)
                .font(.subheadline).lineLimit(compact ? 3 : nil).textSelection(.enabled).accessibilityIdentifier("pipelineTranscript")
            if let result = pipeline.result {
                Text(result.summary).font(.subheadline.weight(.semibold)).accessibilityIdentifier("pipelineSummary")
                if result.model != .rules {
                    Text("These percentages are text estimates, not the chance this call is a scam.").font(.caption)
                }
                // Display all ten behavior outputs; the caller checkpoint has one separate output.
                if compact {
                    Button(expanded ? "Hide text indicators" : "Show text indicators") { expanded.toggle() }
                        .font(.caption)
                }
                if !compact || expanded {
                  ForEach(result.signals) { signal in
                    HStack(alignment: .top) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(signal.label)
                            if let uncertainty = signal.insufficientEvidence {
                                Text("Insufficient evidence: \(Int(uncertainty * 100))%")
                                    .font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        Text(result.model == .rules ? "+\(Int(signal.value))" : "\(Int(signal.value * 100))%")
                            .monospacedDigit()
                    }.font(.caption)
                  }
                }
                if result.wasTrimmed { Text("Only the latest transcript window was checked.").font(.caption2) }
                if result.model != .rules { Text("Checked on this device in \(Int(result.latencyMS)) ms").font(.caption2) }
                if result.text != pipeline.text { Text("Showing the previous checked window while new speech arrives.").font(.caption2) }
            }
            Text("Experimental indicators, not a safety or identity check. Verify unexpected requests independently.")
                .font(.caption2).foregroundStyle(.secondary)
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 16))
    }
}

#if DEBUG
struct TranscriptTestView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var pipeline: TranscriptPipeline
    @StateObject private var source: TranscriptTestSource
    @State private var importing = false
    @State private var typed = ""
    init() {
        let pipeline = TranscriptPipeline()
        _pipeline = StateObject(wrappedValue: pipeline)
        _source = StateObject(wrappedValue: TranscriptTestSource(pipeline: pipeline))
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("Test with your voice or an audio recording. This runs the same local speech and transcript checks used for caller audio.")
                        .font(.subheadline)
                    Picker("Transcript model", selection: Binding(get: { pipeline.model }, set: { pipeline.select($0) })) {
                        ForEach(TranscriptPipeline.Model.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                    }.pickerStyle(.menu).accessibilityIdentifier("pipelineModel")
                    Text("Jev behaviors shows ten text signals. Jev v2 checks caller-only text and was calibrated on synthetic calls.")
                        .font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Button(source.running ? "Stop audio" : "Record my voice") {
                            if source.running { source.stop() } else { Task { await source.record() } }
                        }.buttonStyle(.borderedProminent).accessibilityIdentifier("pipelineRecord")
                        Button("Import audio") { importing = true }.disabled(source.running)
                    }
                    Text("Read a short caller script for testing: “Give me your password. Tell me your verification code. Do not tell your family.”")
                        .font(.caption).foregroundStyle(.secondary)
                    TextField("Or type a caller transcript", text: $typed, axis: .vertical)
                        .textFieldStyle(.roundedBorder).lineLimit(3...8).accessibilityIdentifier("pipelineTypedText")
                    HStack {
                        Button("Use test script") { typed = "Give me your password. Tell me your verification code. Do not tell your family." }
                            .accessibilityIdentifier("pipelineExample")
                        Button("Check text") { pipeline.testText(typed) }
                            .disabled(source.running || typed.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                            .accessibilityIdentifier("pipelineCheckText")
                    }
                    TranscriptStatusView(pipeline: pipeline)
                }.padding(20)
            }
            .navigationTitle("Test transcript pipeline").navigationBarTitleDisplayMode(.inline)
            .tint(Palette.green)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .fileImporter(isPresented: $importing, allowedContentTypes: [.audio]) { outcome in
                switch outcome {
                case .success(let url): source.playFile(url)
                case .failure: break
                }
            }
            .onDisappear { source.stop(); pipeline.cancel() }
            .onChange(of: scenePhase) { phase in if phase != .active { source.stop() } }
        }
    }
}

#endif
