import AVFAudio
import AVFoundation
import SwiftUI

struct ProductionVoicemailView: View {
    @EnvironmentObject private var store: ProductionStore
    @Environment(\.dismiss) private var dismiss
    @State private var selected: VoicemailMessage?
    var body: some View {
        NavigationStack {
            Group {
                if !store.voicemailBackend.isConfigured {
                    PhoneEmptyView(symbol: "recordingtape", title: "Voicemail unavailable", message: "Voicemail is not available in Callshield yet.")
                        .frame(maxHeight: .infinity, alignment: .top)
                } else if store.loadingVoicemail && store.voicemail.isEmpty { ProgressView("Loading voicemail…") }
                else {
                    List {
                        if let error = store.voicemailError {
                            VStack(alignment: .leading, spacing: 12) {
                                Text(error).foregroundStyle(.secondary)
                                Button("Try again") { Task { await store.refreshVoicemail() } }
                            }
                        } else if store.voicemail.isEmpty {
                            PhoneEmptyView(symbol: "recordingtape", title: "No voicemail", message: "New voicemail will appear here.")
                        }
                        ForEach(store.voicemail) { message in
                            Button { selected = message } label: {
                                HStack(spacing: 12) {
                                    Circle().fill(message.isRead ? .clear : Palette.green).frame(width: 8, height: 8)
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(message.caller.name).font(.headline).foregroundStyle(Palette.ink)
                                        Text(message.date.formatted()).font(.caption).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Text(callDuration(message.duration)).font(.caption).foregroundStyle(.secondary)
                                }
                            }.swipeActions {
                                Button("Delete", role: .destructive) { Task { await store.deleteVoicemail(message) } }
                            }
                        }
                    }.listStyle(.plain).refreshable { await store.refreshVoicemail() }
                }
            }
            .navigationTitle("Voicemail")
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .task { await store.refreshVoicemail() }
            .sheet(item: $selected) { message in VoicemailPlaybackView(message: message).environmentObject(store) }
        }.preferredColorScheme(.light).tint(Palette.green)
    }
}

struct VoicemailPlaybackView: View {
    let message: VoicemailMessage
    @EnvironmentObject private var store: ProductionStore
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @State private var player: AVPlayer?
    @State private var playing = false
    @State private var busy = false
    @State private var presented = true
    @State private var allowsPlayback = true
    @State private var error: String?
    @State private var endObserver: NSObjectProtocol?
    @State private var failureObserver: NSObjectProtocol?
    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Avatar(person: message.caller, size: 80)
                Text(message.caller.name).font(.title2.weight(.semibold))
                Text(message.date.formatted()).foregroundStyle(.secondary)
                Text(callDuration(message.duration)).monospacedDigit()
                Button {
                    Task { await togglePlayback() }
                } label: { Label(playing ? "Pause" : "Play", systemImage: playing ? "pause.fill" : "play.fill") }
                .buttonStyle(.borderedProminent).disabled(busy)
                if let error { Text(error).font(.caption).foregroundStyle(.secondary) }
                Spacer()
            }.padding(24)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .onDisappear { presented = false; stopPlayback() }
            .onChange(of: scenePhase) { phase in
                allowsPlayback = phase == .active
                if phase != .active { player?.pause(); playing = false }
            }
        }.tint(Palette.green)
    }
    @MainActor private func togglePlayback() async {
        guard !busy else { return }
        if playing { player?.pause(); playing = false; return }
        busy = true
        defer { busy = false }
        do {
            // Backend returns a short-lived, authenticated HTTPS media URL. There is
            // no microphone recording, local sample media, or cellular voicemail API.
            guard message.audioURL.scheme?.lowercased() == "https" else { throw PhoneError.actionUnavailable }
            try await store.markVoicemailRead(message)
            guard presented, allowsPlayback, store.active == nil else { return }
            if player == nil {
                try AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio)
                try AVAudioSession.sharedInstance().setActive(true)
                let item = AVPlayerItem(url: message.audioURL)
                player = AVPlayer(playerItem: item)
                endObserver = NotificationCenter.default.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main) { _ in
                    Task { @MainActor in playing = false; player?.seek(to: .zero) }
                }
                failureObserver = NotificationCenter.default.addObserver(forName: .AVPlayerItemFailedToPlayToEndTime, object: item, queue: .main) { _ in
                    Task { @MainActor in playing = false; error = "This voicemail couldn’t be played. Please try again." }
                }
            }
            player?.play(); playing = true; error = nil
        } catch { self.error = error.localizedDescription }
    }
    private func stopPlayback() {
        player?.pause(); player = nil; playing = false
        if let endObserver { NotificationCenter.default.removeObserver(endObserver) }
        if let failureObserver { NotificationCenter.default.removeObserver(failureObserver) }
        endObserver = nil; failureObserver = nil
        // Do not deactivate audio if CallKit has already activated a new call.
        if store.active == nil { try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation) }
    }
}
