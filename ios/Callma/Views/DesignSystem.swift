import SwiftUI
import UIKit

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB, red: Double((hex >> 16) & 255) / 255,
                  green: Double((hex >> 8) & 255) / 255, blue: Double(hex & 255) / 255, opacity: 1)
    }
}

enum AppBrand {
    static let name = "callma."
    static let tagline = "call with more peace of mind."
}

enum Palette {
    static func adaptive(_ light: UInt32, _ dark: UInt32) -> Color {
        Color(uiColor: UIColor { traits in
            let value = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: CGFloat((value >> 16) & 255) / 255, green: CGFloat((value >> 8) & 255) / 255, blue: CGFloat(value & 255) / 255, alpha: 1)
        })
    }
    // Clarity Canvas palette from Hackathon-main/src/base.html and its dark classes.
    static let ink = adaptive(0x1B1B1C, 0xEAEAEA)
    static let accent = adaptive(0x172129, 0xBDC8D3)
    static let teal = adaptive(0x4A5D4E, 0xBDC8D3)
    static let lavender = adaptive(0xD9E4EF, 0x2C363F)
    static let sand = adaptive(0xF7DEC8, 0x413223)
    static let coral = adaptive(0xBA1A1A, 0xFFB4AB)
    static let sunshine = adaptive(0x544434, 0xDAC2AD)
    static let canvas = adaptive(0xFBF9F9, 0x1A1A1A)
    static let softAccent = adaptive(0xE0E3E8, 0x2C363F)
    static let surface = adaptive(0xFFFFFF, 0x252525)
    static let secondary = adaptive(0x44474B, 0xC4C7CB)
    static let line = adaptive(0xC4C6CB, 0x44474B)
    static let soft = adaptive(0xF0EDEE, 0x303031)
    static let action = adaptive(0x172129, 0xBDC8D3)
    static let actionInk = adaptive(0xFFFFFF, 0x172129)
    static let missed = adaptive(0xBA1A1A, 0xFFDAD6)
    static let warning = adaptive(0x544434, 0xDAC2AD)
    static let destructive = Color(hex: 0xBA1A1A)

}

extension AvatarColor {
    var background: Color {
        self == .slate ? Palette.soft : Palette.softAccent
    }
    var foreground: Color {
        self == .slate ? Palette.secondary : Palette.accent
    }
}

extension Voice {
    var symbol: String {
        switch self {
        case .ai: return "cpu"
        case .human: return "person"
        case .unknown, .analyzing: return "waveform"
        }
    }
    func foreground(onCall: Bool) -> Color {
        self == .unknown ? Palette.secondary : Palette.accent
    }
    func background(onCall: Bool) -> Color {
        self == .unknown ? Palette.soft : Palette.softAccent
    }
}

struct Avatar: View {
    let person: Person
    var size: CGFloat = 43
    var icon: String? = nil
    var literalInitials = false
    var body: some View {
        Group {
            if let icon { Image(systemName: icon).font(.system(size: size * 0.5)) }
            else if person.initials == "?" && !literalInitials {
                Image(systemName: "person").font(.system(size: size * 0.48))
            } else {
                Text(person.initials).font(.system(size: size * 0.29, weight: size > 64 ? .regular : .semibold))
            }
        }
        .frame(width: size, height: size)
        .foregroundStyle(person.color.foreground)
        .background(person.color.background, in: Circle())
        .accessibilityHidden(true)
    }
}

struct VoiceBadge: View {
    let voice: Voice
    var size: CGFloat = 11
    var onCall = false
    @ScaledMetric(relativeTo: .caption2) private var textScale = 1
    var body: some View {
        HStack(spacing: 3) {
            Image(systemName: voice.symbol)
            Text(voice.label)
        }
        .font(.system(size: max(11, size) * textScale, weight: .medium))
        .foregroundStyle(voice.foreground(onCall: onCall))
        .padding(.horizontal, onCall ? 11 : size >= 12 ? 9 : 4)
        .padding(.vertical, onCall ? 6 : size >= 12 ? 5 : 2)
        .background(voice.background(onCall: onCall), in: RoundedRectangle(cornerRadius: onCall ? 20 : 5))
        .fixedSize(horizontal: true, vertical: false)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(voice.label)
    }
}

struct BrandMark: View {
    var size: CGFloat = 56
    var onDark = false
    var body: some View {
        Text("c.")
            .font(.system(size: size * 0.75, weight: .heavy))
            .tracking(-size * 0.075)
            .padding(.trailing, size * 0.07)
            .frame(width: size, height: size)
            .foregroundStyle(Palette.actionInk)
            .background(Palette.action, in: RoundedRectangle(cornerRadius: size * 0.28))
            .accessibilityHidden(true)
    }
}

struct BrandWordmark: View {
    var onDark = false
    var body: some View {
        HStack(spacing: 8) {
            if onDark { BrandMark(size: 27, onDark: true) }
            Text(AppBrand.name).font(.system(size: onDark ? 17 : 25, weight: .bold)).tracking(-1.25)
                .foregroundStyle(Palette.ink)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(AppBrand.name)
    }
}

struct AppearancePicker: View {
    @AppStorage("callmaAppearance") private var appearance = "system"
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("APPEARANCE").font(.caption.weight(.semibold)).foregroundStyle(Palette.secondary)
            HStack(spacing: 10) {
                option("Light", subtitle: "Off-white · charcoal", value: "light", colors: [0xFBF9F9, 0x172129, 0xE0E3E8])
                option("Dark", subtitle: "Charcoal · soft gray", value: "dark", colors: [0x1A1A1A, 0x252525, 0xEAEAEA])
            }
            Button("Use iPhone appearance") { appearance = "system" }.font(.caption).tint(Palette.accent)
        }
    }
    private func option(_ title: String, subtitle: String, value: String, colors: [UInt32]) -> some View {
        Button { appearance = value } label: {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 0) { ForEach(colors, id: \.self) { color in Color(hex: color) } }
                    .frame(height: 27).clipShape(RoundedRectangle(cornerRadius: 7))
                Text(title).font(.subheadline.weight(.semibold))
                Text(subtitle).font(.caption).foregroundStyle(Palette.secondary)
            }.frame(maxWidth: .infinity, alignment: .leading).padding(12)
                .foregroundStyle(Palette.ink)
                .background(appearance == value ? Palette.softAccent : Palette.surface, in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(appearance == value ? Palette.accent : Palette.line, lineWidth: appearance == value ? 2 : 1))
        }.buttonStyle(.plain).accessibilityAddTraits(appearance == value ? .isSelected : [])
    }
}

struct Footnote: View {
    let text: String
    var shield = false
    var body: some View {
        HStack(alignment: .top, spacing: 4) {
            if shield { Image(systemName: "info.circle") }
            Text(text)
        }
        .font(.caption2)
        .foregroundStyle(Palette.secondary)
        .multilineTextAlignment(.center)
        .frame(maxWidth: .infinity)
        .padding(.top, 20)
    }
}

/// A short press response, including End Call, while respecting Reduce Motion.
struct CallActionStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.91 : 1)
            .opacity(configuration.isPressed ? 0.8 : 1)
            .animation(reduceMotion ? nil : .easeOut(duration: 0.16), value: configuration.isPressed)
    }
}

/// Contextual help stays next to a result, with touch and VoiceOver support.
struct ResultHelpButton: View {
    let title: String
    let message: String
    var onDark = false
    @State private var showing = false
    var body: some View {
        Button { showing = true } label: {
            Image(systemName: "info.circle").font(.system(size: 17))
                .foregroundStyle(Palette.accent)
                .frame(width: 44, height: 44)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("About \(title)")
        .popover(isPresented: $showing) {
            VStack(alignment: .leading, spacing: 16) {
                Text(title).font(.headline)
                Text(message).font(.body).fixedSize(horizontal: false, vertical: true)
                Button("Done") { showing = false }.tint(Palette.accent)
            }
            .padding(24).frame(idealWidth: 300).foregroundStyle(Palette.ink)
            .presentationDetents([.medium])
        }
    }
}


private struct ScaledAppFont: ViewModifier {
    @ScaledMetric(relativeTo: .body) private var scaledSize: CGFloat = 17
    let weight: Font.Weight
    let design: Font.Design
    init(size: CGFloat, weight: Font.Weight, design: Font.Design) {
        _scaledSize = ScaledMetric(wrappedValue: max(11, size), relativeTo: .body)
        self.weight = weight
        self.design = design
    }
    func body(content: Content) -> some View {
        content.font(.system(size: scaledSize, weight: weight, design: design))
    }
}
extension View {
    func scaledFont(size: CGFloat, weight: Font.Weight = .regular, design: Font.Design = .default) -> some View {
        modifier(ScaledAppFont(size: size, weight: weight, design: design))
    }
}
