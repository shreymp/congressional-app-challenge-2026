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
    static func adaptive(_ light: UInt32, _ dark: UInt32, highLight: UInt32? = nil, highDark: UInt32? = nil) -> Color {
        Color(uiColor: UIColor { traits in
            let highContrast = traits.accessibilityContrast == .high
            let value = traits.userInterfaceStyle == .dark
                ? (highContrast ? highDark ?? dark : dark)
                : (highContrast ? highLight ?? light : light)
            return UIColor(red: CGFloat((value >> 16) & 255) / 255, green: CGFloat((value >> 8) & 255) / 255, blue: CGFloat(value & 255) / 255, alpha: 1)
        })
    }
    static let ink = adaptive(0x17243A, 0xEEF4FF, highLight: 0x091525, highDark: 0xFFFFFF)
    static let accent = adaptive(0x195ED9, 0x8EB8FF, highLight: 0x1049AE, highDark: 0xB8D2FF)
    static let onAccent = adaptive(0xFFFFFF, 0x0D1726)
    static let teal = Color(hex: 0x007A60)
    static let lavender = adaptive(0xEAE3FF, 0x302747)
    static let sand = adaptive(0xFFF0C9, 0x3A3224)
    static let coral = Color(hex: 0xBF323A)
    static let sunshine = Color(hex: 0xFFC857)
    static let canvas = adaptive(0xF5F7FA, 0x0D1726)
    static let softAccent = adaptive(0xEDF2F8, 0x22364F)
    static let surface = adaptive(0xFFFFFF, 0x182638)
    static let secondary = adaptive(0x53657D, 0xB5C5DD, highLight: 0x36455B, highDark: 0xDFE9F8)
    static let line = adaptive(0xDCE3EC, 0x344962, highLight: 0x718096, highDark: 0x91A5BF)
    static let missed = adaptive(0xC93F45, 0xFFAAA7)
    static let warning = adaptive(0x78510E, 0xFFD78E)
    static let warningSurface = adaptive(0xFFF3DA, 0x392E19)
}

extension AvatarColor {
    var background: Color {
        switch self {
        case .rose: return Color(hex: 0xFFE3DE)
        case .blue: return Color(hex: 0xDDEBFF)
        case .mint: return Color(hex: 0xCEF5E8)
        case .slate: return Color(hex: 0xEAE3FF)
        }
    }
    var foreground: Color {
        switch self {
        case .rose: return Color(hex: 0x9F392D)
        case .blue: return Color(hex: 0x205AB4)
        case .mint: return Color(hex: 0x006E58)
        case .slate: return Color(hex: 0x6042AD)
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
        case .ai: return onCall ? Color(hex: 0xF6D28D) : Palette.warning
        case .human: return onCall ? Color(hex: 0xDFE9F8) : Palette.ink
        case .unknown: return onCall ? Color(hex: 0xD9E3DF) : Palette.secondary
        case .analyzing: return onCall ? Color(hex: 0xD9E3DF) : Palette.secondary
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
        case .ai: return Palette.warningSurface
        case .human, .unknown, .analyzing: return Palette.softAccent
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
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(voice.label)
    }
}

/// A familiar phone symbol, not a substitute for approved brand artwork.
struct BrandMark: View {
    var size: CGFloat = 56
    var onDark = false
    var body: some View {
        Image(systemName: "phone.fill")
            .font(.system(size: size * 0.43, weight: .medium))
            .foregroundStyle(onDark ? Color.white : Palette.accent)
            .frame(width: size, height: size)
            .background(onDark ? Color.white.opacity(0.08) : Palette.softAccent,
                        in: RoundedRectangle(cornerRadius: size * 0.22))
            .accessibilityHidden(true)
    }
}

struct BrandWordmark: View {
    var onDark = false
    var body: some View {
        HStack(spacing: 8) {
            Text(AppBrand.name).font(.headline)
                .foregroundStyle(onDark ? Color.white : Palette.accent)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(AppBrand.name)
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
                .foregroundStyle(onDark ? Color.white : Palette.accent)
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
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
            .presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
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
