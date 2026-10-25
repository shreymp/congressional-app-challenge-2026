import SwiftUI

struct SettingsScreen: View {
    @EnvironmentObject private var store: CallmaStore
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(spacing: 0) {
                BrandMark()
                Text(AppBrand.name).scaledFont(size: 19, weight: .semibold).padding(.top, 12)
                Text(AppBrand.tagline)
                    .scaledFont(size: 11).foregroundStyle(Palette.secondary).padding(.top, 4)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 9)
            .padding(.bottom, 24)
            .padding(.horizontal, 12)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: 24))
            .padding(.bottom, 20)

            AppearancePicker().padding(.bottom, 20)
            VStack(spacing: 0) {
                Toggle("Larger text", isOn: $store.largeText)
                    .tint(Palette.teal)
                    .accessibilityIdentifier("largerTextToggle")
                    .frame(minHeight: 47)
                Divider()
                setting("Calling", value: "Demo")
                Divider()
                setting("Voice labels", value: "Simulated")
            }
            .scaledFont(size: store.largeText ? 14 : 12)
            .padding(.horizontal, 13)
            .background(Palette.softAccent, in: RoundedRectangle(cornerRadius: 12))

            Text("This prototype uses sample calls and simulated results. Real incoming calls and voice analysis require connected services.")
                .scaledFont(size: 11)
                .foregroundStyle(Palette.secondary)
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
            Text(value).scaledFont(size: 11).foregroundStyle(Palette.secondary)
        }
        .frame(minHeight: 47)
    }
}
