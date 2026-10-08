import SwiftUI

struct SettingsScreen: View {
    @EnvironmentObject private var store: CallshieldStore
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(spacing: 0) {
                BrandMark()
                Text("Callshield").font(.system(size: 19, weight: .semibold)).padding(.top, 12)
                Text("More clarity for every incoming call.")
                    .font(.system(size: 11)).foregroundStyle(Color(hex: 0x89968D)).padding(.top, 4)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 9)
            .padding(.bottom, 24)

            VStack(spacing: 0) {
                Toggle("Larger text", isOn: $store.largeText)
                    .tint(Color(hex: 0x34C759))
                    .accessibilityIdentifier("largerTextToggle")
                    .frame(minHeight: 47)
                Divider()
                setting("Calling mode", value: "Incoming only")
                Divider()
                setting("Connection", value: "Demo")
            }
            .font(.system(size: store.largeText ? 14 : 12))
            .padding(.horizontal, 13)
            .background(Color(hex: 0xF6F7F6), in: RoundedRectangle(cornerRadius: 12))

            Text("UNDERSTANDING VOICE LABELS")
                .font(.system(size: 9)).tracking(1)
                .foregroundStyle(Color(hex: 0x9AA19C))
                .accessibilityAddTraits(.isHeader)
                .padding(.top, 23).padding(.bottom, 10)
            ForEach([Voice.ai, .human, .unknown], id: \.self) { voice in
                VStack(alignment: .leading, spacing: 6) {
                    VoiceBadge(voice: voice)
                    Text(voice.explanation)
                        .font(.system(size: 11))
                        .foregroundStyle(Color(hex: 0x8B958E))
                        .lineSpacing(4)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.vertical, 7)
            }
            Text("This prototype uses sample calls and simulated results. Real incoming calls and voice analysis require connected services.")
                .font(.system(size: 11))
                .foregroundStyle(Color(hex: 0x8B958E))
                .lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 12)
                .overlay(alignment: .top) { Rectangle().fill(Palette.line).frame(height: 1) }
                .padding(.top, 7)
        }
    }

    private func setting(_ label: String, value: String) -> some View {
        HStack {
            Text(label)
            Spacer()
            Text(value).font(.system(size: 11)).foregroundStyle(Color(hex: 0x89948D))
        }
        .frame(minHeight: 47)
    }
}
