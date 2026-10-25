import SwiftUI
import UIKit

// "Paper & Midnight" design system. Screens use these semantic tokens and components only;
// a raw hex value belongs here and nowhere else. See UI_REVAMP.md for the rules.

private extension UIColor {
    convenience init(hex: UInt32) {
        self.init(red: CGFloat((hex >> 16) & 255) / 255, green: CGFloat((hex >> 8) & 255) / 255,
                  blue: CGFloat(hex & 255) / 255, alpha: 1)
    }
}

extension Color {
    /// A color that follows the current appearance. Increase Contrast swaps in the stronger values when given.
    init(light: UInt32, dark: UInt32, contrastLight: UInt32? = nil, contrastDark: UInt32? = nil) {
        self.init(uiColor: UIColor { traits in
            let dark_ = traits.userInterfaceStyle == .dark
            if traits.accessibilityContrast == .high, let value = dark_ ? contrastDark : contrastLight {
                return UIColor(hex: value)
            }
            return UIColor(hex: dark_ ? dark : light)
        })
    }
}

enum Theme {
    static let backgroundPrimary = Color(light: 0xF4ECE0, dark: 0x1C1D1F)
    static let backgroundSurface = Color(light: 0xFFFCF6, dark: 0x2B2D30)
    static let backgroundElevated = Color(light: 0xFFFFFF, dark: 0x35373B)

    static let textPrimary = Color(light: 0x20252B, dark: 0xF7F4EF)
    static let textSecondary = Color(light: 0x54606A, dark: 0xC1C7CA, contrastLight: 0x3A434B, contrastDark: 0xE2E5E7)

    static let actionPrimary = Color(light: 0x25262A, dark: 0xA8C8EE)
    static let actionPrimaryText = Color(light: 0xFFFFFF, dark: 0x152436)
    static let actionAccent = Color(light: 0x315F93, dark: 0xA8C8EE, contrastLight: 0x234A75, contrastDark: 0xCFE1F7)
    static let actionAccentBackground = Color(light: 0xE7ECF1, dark: 0x253B55)
    static let actionDestructive = Color(light: 0xB43D46, dark: 0xB43D46)
    /// Missed-call names and destructive text links (the fill above is too dark to read as text in dark mode).
    static let textDestructive = Color(light: 0xB43D46, dark: 0xFF8F98)
    static let actionAccept = Color(light: 0x1F7A4D, dark: 0x1F7A4D)
    static let brandCopper = Color(light: 0x955137, dark: 0xE7B190)

    static let borderDecorative = Color(light: 0xE3DCD3, dark: 0x4B4D51, contrastLight: 0x8B8177, contrastDark: 0x858A91)
    static let borderInteractive = Color(light: 0x8B8177, dark: 0x858A91, contrastLight: 0x5E564F, contrastDark: 0xB0B5BB)

    static let statusHuman = Color(light: 0x207057, dark: 0x9AD9C0)
    static let statusHumanBackground = Color(light: 0xE6F3EC, dark: 0x24443B)
    static let statusAI = Color(light: 0xA93A44, dark: 0xFF9BA5)
    static let statusAIBackground = Color(light: 0xFBEAEC, dark: 0x4A2B30)
    static let statusAnalyzing = Color(light: 0x315F93, dark: 0xA5C8F5)
    static let statusAnalyzingBackground = Color(light: 0xE7ECF1, dark: 0x253B55)
    static let statusInconclusive = Color(light: 0x94601E, dark: 0xF1C98B)
    static let statusInconclusiveBackground = Color(light: 0xFAF1E0, dark: 0x473A29)

    static let cornerRadius: CGFloat = 12
    static let cardRadius: CGFloat = 20
    static let margin: CGFloat = 20
}

/// The person's choice in Settings; nil follows the system.
enum AppearanceChoice: String, CaseIterable {
    case system = "System", light = "Light", dark = "Dark"
    static let storageKey = "appearance"
    var colorScheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light: return .light
        case .dark: return .dark
        }
    }
}

extension AvatarColor {
    var background: Color {
        switch self {
        case .rose: return Color(light: 0xF3E0D5, dark: 0x4A3329)
        case .blue: return Color(light: 0xE7ECF1, dark: 0x253B55)
        case .mint: return Color(light: 0xE5ECE7, dark: 0x2E3B34)
        case .slate: return Color(light: 0xE3DCD3, dark: 0x3E4044)
        }
    }
    var foreground: Color {
        switch self {
        case .rose: return Color(light: 0x955137, dark: 0xE7B190)
        case .blue: return Color(light: 0x315F93, dark: 0xA8C8EE)
        case .mint: return Color(light: 0x537261, dark: 0xB5CDBF)
        case .slate: return Color(light: 0x54606A, dark: 0xC1C7CA)
        }
    }
}

extension Voice {
    /// Each state has its own shape so the result never depends on color alone.
    var symbol: String {
        switch self {
        case .ai: return "exclamationmark.triangle.fill"
        case .human: return "person.fill"
        case .unknown: return "questionmark.circle.fill"
        case .analyzing: return "waveform"
        }
    }
    var foreground: Color {
        switch self {
        case .ai: return Theme.statusAI
        case .human: return Theme.statusHuman
        case .unknown: return Theme.statusInconclusive
        case .analyzing: return Theme.statusAnalyzing
        }
    }
    var background: Color {
        switch self {
        case .ai: return Theme.statusAIBackground
        case .human: return Theme.statusHumanBackground
        case .unknown: return Theme.statusInconclusiveBackground
        case .analyzing: return Theme.statusAnalyzingBackground
        }
    }
}

// MARK: - Building blocks

struct Avatar: View {
    let person: Person
    var size: CGFloat = 52
    var icon: String? = nil
    var literalInitials = false
    var body: some View {
        Group {
            if let icon { Image(systemName: icon).font(.system(size: size * 0.42, weight: .medium)) }
            else if person.initials == "?" && !literalInitials {
                Image(systemName: "person.fill").font(.system(size: size * 0.42))
            } else {
                Text(person.initials).font(.system(size: size * 0.34, weight: .semibold))
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
    var title: String? = nil
    var large = false
    var body: some View {
        Label { Text(title ?? voice.label) } icon: { Image(systemName: voice.symbol) }
            .font(large ? .body.weight(.semibold) : .subheadline.weight(.semibold))
            .foregroundStyle(voice.foreground)
            .padding(.horizontal, large ? 14 : 10)
            .padding(.vertical, large ? 8 : 5)
            .background(voice.background, in: Capsule())
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(title ?? voice.label)
    }
}

/// The one place a voice result is explained in full: on the call and in call details.
struct VoiceStatusCard<Footer: View>: View {
    let voice: Voice
    let heading: String
    let message: String
    var messageID: String? = nil
    var assessmentTitle: String? = nil
    var warning: Bool = false
    @ViewBuilder var footer: Footer
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label(heading, systemImage: "waveform.badge.magnifyingglass")
                .font(.callout.weight(.semibold)).foregroundStyle(Theme.textSecondary)
                .accessibilityAddTraits(.isHeader)
            HStack(spacing: 14) {
                Image(systemName: voice.symbol)
                    .font(.system(size: 24, weight: .semibold))
                    .frame(width: 52, height: 52)
                    .background(voice.background, in: Circle())
                    .accessibilityHidden(true)
                Text(assessmentTitle ?? voice.label).font(.title2.weight(.semibold))
            }
            .foregroundStyle(warning ? Theme.statusAI : voice.foreground)
            Text(message).font(.body).foregroundStyle(Theme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier(messageID ?? "")
            if voice == .ai || warning { SafetySteps() }
            footer
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .multilineTextAlignment(.leading)
        .card(background: voice == .ai || warning ? Theme.statusAIBackground : Theme.backgroundSurface,
              border: voice == .ai || warning ? Theme.statusAI : Theme.borderDecorative)
    }
}

extension VoiceStatusCard where Footer == EmptyView {
    init(voice: Voice, heading: String, message: String, messageID: String? = nil) {
        self.init(voice: voice, heading: heading, message: message, messageID: messageID) { EmptyView() }
    }
}

/// Plain next steps shown with a Likely AI result. Advice only; it never claims the call is a scam.
struct SafetySteps: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("What to do").font(.headline).foregroundStyle(Theme.textPrimary)
            step("hand.raised.fill", "Don’t share passwords, bank details or codes.")
            step("phone.arrow.up.right", "If unsure, hang up and call back on a number you trust.")
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.backgroundSurface, in: RoundedRectangle(cornerRadius: Theme.cornerRadius))
    }
    private func step(_ symbol: String, _ text: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Image(systemName: symbol).foregroundStyle(Theme.statusAI).accessibilityHidden(true)
            Text(text).font(.body).foregroundStyle(Theme.textPrimary).fixedSize(horizontal: false, vertical: true)
        }
    }
}

struct BrandMark: View {
    var body: some View {
        Image(systemName: "checkmark.shield.fill")
            .font(.system(size: 30))
            .foregroundStyle(.white)
            .frame(width: 60, height: 60)
            .background(Theme.brandCopper, in: RoundedRectangle(cornerRadius: 16))
            .environment(\.colorScheme, .light)
            .accessibilityHidden(true)
    }
}

/// Small brand line above each screen title. Copper is reserved for this mark.
struct Wordmark: View {
    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "checkmark.shield.fill").foregroundStyle(Theme.brandCopper)
            // The spec's lowercase "callma." lettering; the copper full stop is the brand detail.
            (Text("callma").foregroundColor(Theme.textPrimary) + Text(".").foregroundColor(Theme.brandCopper))
                .font(.title3.weight(.bold))
        }
        .font(.headline)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Callma")
    }
}

struct ScreenTitle: View {
    let text: String
    var body: some View {
        Text(text).font(.largeTitle.weight(.semibold)).foregroundStyle(Theme.textPrimary)
            .accessibilityAddTraits(.isHeader)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct SectionHeader: View {
    let text: String
    var body: some View {
        Text(text).font(.title3.weight(.semibold)).foregroundStyle(Theme.textPrimary)
            .accessibilityAddTraits(.isHeader)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 8)
    }
}

struct Footnote: View {
    let text: String
    var symbol: String? = nil
    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            if let symbol { Image(systemName: symbol).accessibilityHidden(true) }
            Text(text).fixedSize(horizontal: false, vertical: true)
        }
        .font(.callout)
        .foregroundStyle(Theme.textSecondary)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 8)
    }
}

struct EmptyStateView: View {
    let symbol: String
    let title: String
    let message: String
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: symbol).font(.system(size: 36)).foregroundStyle(Theme.textSecondary)
                .accessibilityHidden(true)
            Text(title).font(.title3.weight(.semibold)).foregroundStyle(Theme.textPrimary)
            Text(message).font(.body).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 24).padding(.vertical, 40)
    }
}

extension View {
    /// Warm White surface with a decorative edge: the standard container for grouped content.
    func card(padding: CGFloat = 20, background: Color = Theme.backgroundSurface,
              border: Color = Theme.borderDecorative) -> some View {
        self.padding(padding)
            .background(background, in: RoundedRectangle(cornerRadius: Theme.cardRadius))
            .overlay(RoundedRectangle(cornerRadius: Theme.cardRadius).strokeBorder(border, lineWidth: 1))
    }
}

// MARK: - Buttons

enum ActionKind { case primary, secondary, destructive, accept }

struct ActionButtonStyle: ButtonStyle {
    var kind: ActionKind = .primary
    func makeBody(configuration: Configuration) -> some View {
        ActionButtonBody(kind: kind, configuration: configuration)
    }
}

private struct ActionButtonBody: View {
    let kind: ActionKind
    let configuration: ButtonStyle.Configuration
    @Environment(\.isEnabled) private var isEnabled
    var body: some View {
        configuration.label
            .font(.body.weight(.semibold))
            .multilineTextAlignment(.center)
            .frame(maxWidth: .infinity, minHeight: 56)
            .padding(.horizontal, 20)
            .foregroundStyle(foreground)
            .background(background, in: RoundedRectangle(cornerRadius: Theme.cornerRadius))
            .overlay {
                if kind == .secondary {
                    RoundedRectangle(cornerRadius: Theme.cornerRadius).strokeBorder(Theme.borderInteractive, lineWidth: 1.5)
                }
            }
            .opacity(isEnabled ? (configuration.isPressed ? 0.8 : 1) : 0.45)
            .contentShape(RoundedRectangle(cornerRadius: Theme.cornerRadius))
    }
    private var foreground: Color {
        switch kind {
        case .primary: return Theme.actionPrimaryText
        case .secondary: return Theme.textPrimary
        case .destructive, .accept: return .white
        }
    }
    private var background: Color {
        switch kind {
        case .primary: return Theme.actionPrimary
        case .secondary: return Theme.backgroundSurface
        case .destructive: return Theme.actionDestructive
        case .accept: return Theme.actionAccept
        }
    }
}

/// Round call control with its name underneath. Toggles show On by filling in, not only by color.
struct CallControlButton: View {
    enum Style { case accept, decline, toggle(Bool) }
    let title: String
    let symbol: String
    var style: Style = .toggle(false)
    var size: CGFloat = 76
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            VStack(spacing: 10) {
                Image(systemName: symbol)
                    .font(.system(size: size * 0.38, weight: .semibold))
                    .foregroundStyle(iconColor)
                    .frame(width: size, height: size)
                    .background(fill, in: Circle())
                    .overlay {
                        if case .toggle(false) = style { Circle().strokeBorder(Theme.borderInteractive, lineWidth: 1.5) }
                    }
                Text(title).font(.callout.weight(.semibold)).foregroundStyle(Theme.textPrimary)
                    .lineLimit(1).minimumScaleFactor(0.8)
            }
            .frame(minWidth: size + 8)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityValue(toggleValue)
    }
    private var fill: Color {
        switch style {
        case .accept: return Theme.actionAccept
        case .decline: return Theme.actionDestructive
        case .toggle(let on): return on ? Theme.actionPrimary : Theme.backgroundSurface
        }
    }
    private var iconColor: Color {
        switch style {
        case .accept, .decline: return .white
        case .toggle(let on): return on ? Theme.actionPrimaryText : Theme.textPrimary
        }
    }
    private var toggleValue: String {
        if case .toggle(let on) = style { return on ? "On" : "Off" }
        return ""
    }
}

// MARK: - Shared controls

/// Large two- or three-way choice. The selected option is filled dark, not only recolored.
struct ChoiceBar<Value: Hashable>: View {
    let options: [(value: Value, title: String, accessibility: String)]
    @Binding var selection: Value
    var identifier: (Value) -> String = { _ in "" }
    var body: some View {
        HStack(spacing: 4) {
            ForEach(options, id: \.value) { option in
                let selected = selection == option.value
                Button { selection = option.value } label: {
                    Text(option.title)
                        .font(.body.weight(.semibold))
                        .lineLimit(1).minimumScaleFactor(0.8)
                        .foregroundStyle(selected ? Theme.actionPrimaryText : Theme.textPrimary)
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .background(selected ? Theme.actionPrimary : .clear, in: RoundedRectangle(cornerRadius: 10))
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(option.accessibility)
                .accessibilityIdentifier(identifier(option.value))
                .accessibilityAddTraits(selected ? .isSelected : [])
            }
        }
        .padding(4)
        .background(Theme.backgroundSurface, in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Theme.borderDecorative, lineWidth: 1))
    }
}

struct FilterBar: View {
    @Binding var selection: CallFilter
    var body: some View {
        ChoiceBar(options: [(CallFilter.all, "All calls", "All calls"), (.missed, "Missed", "Missed calls")],
                  selection: $selection, identifier: { "filter\($0.rawValue)" })
    }
}

struct PhoneSearchField: View {
    @Binding var text: String
    let label: String
    var placeholder = "Search"
    var identifier: String? = nil
    @FocusState private var focused: Bool
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "magnifyingglass").font(.body.weight(.semibold)).foregroundStyle(Theme.textSecondary)
                .accessibilityHidden(true)
            TextField(placeholder, text: $text)
                .font(.body).foregroundStyle(Theme.textPrimary)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
                .submitLabel(.search).onSubmit { focused = false }
                .focused($focused)
                .accessibilityLabel(label)
                .accessibilityIdentifier(identifier ?? "")
            if !text.isEmpty {
                Button { text = "" } label: {
                    Image(systemName: "xmark.circle.fill").font(.title3).frame(width: 44, height: 44)
                }
                .buttonStyle(.plain).foregroundStyle(Theme.textSecondary).accessibilityLabel("Clear search")
            }
        }
        .padding(.leading, 16).padding(.trailing, 4)
        .frame(minHeight: 52)
        .background(Theme.backgroundSurface, in: RoundedRectangle(cornerRadius: Theme.cornerRadius))
        .overlay(RoundedRectangle(cornerRadius: Theme.cornerRadius)
            .strokeBorder(focused ? Theme.actionAccent : Theme.borderInteractive, lineWidth: focused ? 2 : 1))
        .contentShape(Rectangle())
        .onTapGesture { focused = true }
    }
}

/// Bottom navigation. The selected tab gets a filled pill as well as the accent color.
struct AppTabBar<Tab: Hashable>: View {
    let tabs: [Tab]
    @Binding var selection: Tab
    let title: (Tab) -> String
    let symbol: (Tab) -> String
    let identifier: (Tab) -> String
    var body: some View {
        HStack(spacing: 0) {
            ForEach(tabs, id: \.self) { tab in
                let selected = selection == tab
                Button { selection = tab } label: {
                    VStack(spacing: 4) {
                        Image(systemName: symbol(tab))
                            .font(.system(size: 22, weight: selected ? .semibold : .regular))
                            .frame(width: 58, height: 32)
                            .background(selected ? Theme.actionAccentBackground : .clear, in: Capsule())
                        Text(title(tab)).font(.footnote.weight(.semibold)).lineLimit(1).minimumScaleFactor(0.75)
                    }
                    .foregroundStyle(selected ? Theme.actionAccent : Theme.textSecondary)
                    .frame(maxWidth: .infinity, minHeight: 60)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(title(tab))
                .accessibilityIdentifier(identifier(tab))
                .accessibilityAddTraits(selected ? .isSelected : [])
            }
        }
        .padding(.horizontal, 8).padding(.top, 8).padding(.bottom, 4)
        .dynamicTypeSize(...DynamicTypeSize.xxLarge)
        .background(Theme.backgroundSurface.ignoresSafeArea(edges: .bottom))
        .overlay(alignment: .top) { Rectangle().fill(Theme.borderDecorative).frame(height: 1) }
    }
}

/// A grouped row container: Warm White card with decorative dividers between rows.
struct GroupedRows<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        VStack(spacing: 0) { content }
            .padding(.horizontal, 16)
            .background(Theme.backgroundSurface, in: RoundedRectangle(cornerRadius: Theme.cardRadius))
            .overlay(RoundedRectangle(cornerRadius: Theme.cardRadius).strokeBorder(Theme.borderDecorative, lineWidth: 1))
    }
}

struct RowDivider: View {
    var inset: CGFloat = 0
    var body: some View { Rectangle().fill(Theme.borderDecorative).frame(height: 1).padding(.leading, inset) }
}

/// A label-and-value line inside a grouped card.
struct InfoRow: View {
    let label: String
    let value: String
    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(label).foregroundStyle(Theme.textSecondary)
                Spacer(minLength: 12)
                Text(value).fontWeight(.medium).foregroundStyle(Theme.textPrimary).multilineTextAlignment(.trailing)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text(label).foregroundStyle(Theme.textSecondary)
                Text(value).fontWeight(.medium).foregroundStyle(Theme.textPrimary)
            }.frame(maxWidth: .infinity, alignment: .leading)
        }
        .font(.body)
        .padding(.vertical, 14)
        .frame(minHeight: 52)
    }
}

/// A person row used by Recents, Contacts and Favorites. With large text the time moves under the details
/// so names and labels keep the full width instead of wrapping word by word.
struct PersonRow<Detail: View>: View {
    let person: Person
    var nameColor: Color = Theme.textPrimary
    var trailing: String? = nil
    @ViewBuilder var detail: Detail
    @Environment(\.dynamicTypeSize) private var typeSize
    var body: some View {
        let stacked = typeSize >= .xLarge
        HStack(spacing: 14) {
            Avatar(person: person)
            VStack(alignment: .leading, spacing: 6) {
                Text(person.name).font(.body.weight(.semibold)).foregroundStyle(nameColor).lineLimit(2)
                detail
                if stacked, let trailing { Text(trailing).font(.subheadline).foregroundStyle(Theme.textSecondary) }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if !stacked, let trailing {
                Text(trailing).font(.subheadline).foregroundStyle(Theme.textSecondary).fixedSize()
            }
            Image(systemName: "chevron.right").font(.body.weight(.semibold)).foregroundStyle(Theme.textSecondary)
                .accessibilityHidden(true)
        }
        .padding(.vertical, 14)
        .frame(minHeight: 76)
        .contentShape(Rectangle())
    }
}

/// "10:42 AM" today, "Yesterday", then "Oct 18": the words people use, not a timestamp.
func friendlyDate(_ date: Date) -> String {
    let calendar = Calendar.current
    if calendar.isDateInToday(date) { return date.formatted(date: .omitted, time: .shortened) }
    if calendar.isDateInYesterday(date) { return "Yesterday" }
    return date.formatted(.dateTime.month(.abbreviated).day())
}
