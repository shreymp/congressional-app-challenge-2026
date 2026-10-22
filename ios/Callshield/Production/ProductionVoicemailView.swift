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
                                Text(error).font(.body).foregroundStyle(Theme.textSecondary)
                                Button("Try again") { Task { await store.refreshVoicemail() } }
                                    .buttonStyle(ActionButtonStyle(kind: .secondary))
                            }.listRowBackground(Color.clear)
                        } else if store.voicemail.isEmpty {
                            PhoneEmptyView(symbol: "recordingtape", title: "No voicemail", message: "New voicemail will appear here.")
                                .listRowBackground(Color.clear)
                        }
                        ForEach(store.voicemail) { message in
                            Button { selected = message } label: {
                                HStack(spacing: 12) {
                                    Circle().fill(message.isRead ? .clear : Theme.actionAccent).frame(width: 12, height: 12)
                                        .accessibilityHidden(true)
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(message.caller.name).font(.body.weight(message.isRead ? .medium : .bold))
                                            .foregroundStyle(Theme.textPrimary)
                                        Text(message.isRead ? friendlyDate(message.date) : "New · \(friendlyDate(message.date))")
                                            .font(.callout).foregroundStyle(Theme.textSecondary)
                                    }
                                    Spacer()
                                    Text(callDuration(message.duration)).font(.callout).monospacedDigit().foregroundStyle(Theme.textSecondary)
                                    Image(systemName: "play.circle.fill").font(.title2).foregroundStyle(Theme.actionAccent)
                                        .accessibilityHidden(true)
                                }
                                .frame(minHeight: 60)
                            }
                            .listRowBackground(Theme.backgroundSurface)
                            .swipeActions {
                                Button("Delete", role: .destructive) { Task { await store.deleteVoicemail(message) } }
                            }
                        }
                    }.listStyle(.insetGrouped).scrollContentBackground(.hidden).refreshable { await store.refreshVoicemail() }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.backgroundPrimary.ignoresSafeArea())
            .navigationTitle("Voicemail")
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() }.font(.body.weight(.semibold)) } }
            .task { await store.refreshVoicemail() }
            .sheet(item: $selected) { message in VoicemailPlaybackView(message: message).environmentObject(store) }
        }.tint(Theme.actionAccent)
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
            VStack(spacing: 16) {
                Avatar(person: message.caller, size: 88)
                Text(message.caller.name).font(.title.weight(.semibold)).foregroundStyle(Theme.textPrimary)
                    .multilineTextAlignment(.center)
                Text(message.date.formatted(date: .abbreviated, time: .shortened)).font(.title3).foregroundStyle(Theme.textSecondary)
                Text(callDuration(message.duration)).font(.title3).monospacedDigit().foregroundStyle(Theme.textSecondary)
                Button {
                    Task { await togglePlayback() }
                } label: { Label(playing ? "Pause" : "Play message", systemImage: playing ? "pause.fill" : "play.fill") }
                .buttonStyle(ActionButtonStyle()).disabled(busy).padding(.top, 8)
                if let error { Text(error).font(.body).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center) }
                Spacer()
            }.padding(24)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.backgroundPrimary.ignoresSafeArea())
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() }.font(.body.weight(.semibold)) } }
            .onDisappear { presented = false; stopPlayback() }
            .onChange(of: scenePhase) { phase in
                allowsPlayback = phase == .active
                if phase != .active { player?.pause(); playing = false }
            }
        }.tint(Theme.actionAccent)
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
