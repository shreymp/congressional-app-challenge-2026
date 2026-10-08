import SwiftUI

struct ProductionCallView: View {
    let call: PhoneCall
    @EnvironmentObject private var store: ProductionStore
    @State private var showingKeypad = false
    @State private var busy = false
    private let clock = Timer.publish(every: 1, on: .main, in: .common).autoconnect()
    @State private var now = Date()
    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 18) {
                    Label("Callshield", systemImage: "checkmark.shield").font(.subheadline).foregroundStyle(Color(hex: 0xD3DFD7))
                    Avatar(person: call.person, size: 80).padding(.top, 12)
                    Text(call.person.name).font(.title.weight(.medium))
                    Text(call.person.number).font(.subheadline).foregroundStyle(Color(hex: 0xBDCCC3))
                    Text(status).monospacedDigit().foregroundStyle(Color(hex: 0x9FB5A8))
                    if call.connectedAt != nil {
                        VStack(spacing: 10) {
                            VoiceBadge(voice: call.voice, size: 13, onCall: true)
                            Text(assessment).font(.caption).foregroundStyle(Color(hex: 0xD0DCD5))
                            Text("Not an identity check").font(.caption2).foregroundStyle(Color(hex: 0x8DA597))
                        }.padding(16).frame(maxWidth: .infinity)
                            .background(.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 18))
                    }
                    Spacer(minLength: 20)
                    if call.stage == .incoming {
                        HStack {
                            action("Decline", "phone.down.fill", color: Color(hex: 0xF44E54)) { try await store.coordinator.end() }
                            Spacer()
                            action("Accept", "phone.fill", color: Color(hex: 0x32C968)) { try await store.coordinator.answer() }
                        }.padding(.horizontal, 12)
                    } else {
                        if showingKeypad {
                            PhoneKeypad { digit in perform { try await store.coordinator.sendDTMF(digit) } }
                        } else {
                            HStack(spacing: 24) {
                                action(call.muted ? "unmute" : "mute", call.muted ? "mic.slash" : "mic", selected: call.muted) {
                                    try await store.coordinator.setMuted(!call.muted)
                                }
                                action("speaker", "speaker.wave.2", selected: call.speaker) {
                                    try store.coordinator.setSpeaker(!call.speaker)
                                }
                                action(call.stage == .held ? "resume" : "hold", "pause", selected: call.stage == .held) {
                                    try await store.coordinator.setHeld(call.stage != .held)
                                }
                            }.disabled(call.connectedAt == nil)
                        }
                        Button(showingKeypad ? "Hide keypad" : "Keypad") { showingKeypad.toggle() }
                            .disabled(call.connectedAt == nil).padding(8)
                        action("End call", "phone.down.fill", color: Color(hex: 0xF44E54)) { try await store.coordinator.end() }
                    }
                }
                .padding(28).frame(maxWidth: 500).frame(minHeight: geometry.size.height).frame(maxWidth: .infinity)
            }.scrollIndicators(.hidden)
        }
        .multilineTextAlignment(.center).foregroundStyle(.white)
        .background(RadialGradient(colors: [Color(hex: 0x3A554C), Color(hex: 0x25382F), Color(hex: 0x131F1C)], center: .topLeading, startRadius: 0, endRadius: 700).ignoresSafeArea())
        .onReceive(clock) { now = $0 }
    }
    private var status: String {
        switch call.stage {
        case .incoming: return "Incoming call"
        case .connecting: return "Connecting…"
        case .held: return "On hold"
        case .connected: return callDuration(call.connectedAt.map { max(0, Int(now.timeIntervalSince($0))) } ?? 0)
        }
    }
    private var assessment: String {
        switch call.voice {
        case .analyzing: return "Checking the caller’s voice…"
        case .ai: return "This voice may be AI-generated."
        case .human: return "This voice appears to be human."
        case .unknown: return "A voice assessment is not available."
        }
    }
    private func action(_ title: String, _ symbol: String, color: Color = .white.opacity(0.13), selected: Bool = false,
                        operation: @escaping () async throws -> Void) -> some View {
        Button { perform(operation) } label: {
            VStack(spacing: 9) {
                Image(systemName: symbol).font(.system(size: 27))
                    .foregroundStyle(selected ? Color(hex: 0x273C31) : .white)
                    .frame(width: 64, height: 64).background(selected ? .white : color, in: Circle())
                Text(title).font(.caption)
            }
        }.buttonStyle(.plain).disabled(busy).accessibilityValue(selected ? "On" : "Off")
    }
    private func perform(_ operation: @escaping () async throws -> Void) {
        guard !busy else { return }
        busy = true
        Task {
            defer { busy = false }
            do { try await operation() }
            catch { store.errorMessage = error.localizedDescription }
        }
    }
}
