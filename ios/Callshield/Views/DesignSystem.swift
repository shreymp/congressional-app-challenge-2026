import SwiftUI

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB, red: Double((hex >> 16) & 255) / 255,
                  green: Double((hex >> 8) & 255) / 255, blue: Double(hex & 255) / 255, opacity: 1)
    }
}

enum Palette {
    static let ink = Color(hex: 0x151719)
    static let green = Color(hex: 0x176EAA)
    static let secondary = Color(hex: 0x617069)
    static let line = Color(hex: 0xF0F0F1)
    static let missed = Color(hex: 0xE45954)
}

extension AvatarColor {
    var background: Color {
        switch self {
        case .rose: return Color(hex: 0xF4E6E3)
        case .blue: return Color(hex: 0xE5EDF5)
        case .mint: return Color(hex: 0xE3EEE8)
        case .slate: return Color(hex: 0xEEEFF1)
        }
    }
    var foreground: Color {
        switch self {
        case .rose: return Color(hex: 0xAE7B70)
        case .blue: return Color(hex: 0x6A8AAB)
        case .mint: return Color(hex: 0x739786)
        case .slate: return Color(hex: 0x8D949B)
        }
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
        switch self {
        case .ai: return Color(hex: onCall ? 0xF6D28D : 0xA27628)
        case .human: return Color(hex: onCall ? 0xAFE4C6 : 0x43886C)
        case .unknown: return Color(hex: onCall ? 0xD9E3DF : 0x80868E)
        case .analyzing: return Color(hex: onCall ? 0xD9E3DF : 0x7590B2)
        }
    }
    func background(onCall: Bool) -> Color {
        if onCall {
            switch self {
            case .ai: return Color(hex: 0xDCA953).opacity(0.13)
            case .human: return Color(hex: 0x90D4AE).opacity(0.13)
            case .unknown, .analyzing: return .white.opacity(0.09)
            }
        }
        switch self {
        case .ai: return Color(hex: 0xFBF1DD)
        case .human: return Color(hex: 0xEAF5EE)
        case .unknown: return Color(hex: 0xF0F1F3)
        case .analyzing: return Color(hex: 0xEDF2F9)
        }
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
    var size: CGFloat = 10
    var onCall = false
    @ScaledMetric(relativeTo: .caption2) private var textScale = 1
    var body: some View {
        HStack(spacing: 3) {
            Image(systemName: voice.symbol)
            Text(voice.label)
        }
        .font(.system(size: size * textScale, weight: .medium))
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
    var body: some View {
        Image(systemName: "checkmark.shield")
            .font(.system(size: 28))
            .foregroundStyle(.white)
            .frame(width: 52, height: 55)
            .background(Color(hex: 0x176EAA), in: RoundedRectangle(cornerRadius: 16))
            .accessibilityHidden(true)
    }
}

struct Footnote: View {
    let text: String
    var shield = false
    var body: some View {
        HStack(alignment: .top, spacing: 4) {
            if shield { Image(systemName: "checkmark.shield") }
            Text(text)
        }
        .font(.caption2)
        .foregroundStyle(Color(hex: 0xA1A7A2))
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
