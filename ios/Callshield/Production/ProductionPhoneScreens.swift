import SwiftUI
import UIKit

struct ProductionRecentsView: View {
    @EnvironmentObject private var store: ProductionStore
    var body: some View {
        List {
            Section {
                ProtectionStatusCard(active: store.coordinator.backend.isConfigured)
                    .listRowInsets(EdgeInsets()).listRowBackground(Color.clear)
            }
            Section {
                VStack(spacing: 12) {
                    FilterBar(selection: $store.filter)
                    PhoneSearchField(text: $store.search, label: "Search recent calls", placeholder: "Search by name or number")
                }
                .listRowInsets(EdgeInsets()).listRowBackground(Color.clear)
            }
            Section {
                if store.visibleHistory.isEmpty {
                    EmptyStateView(symbol: "clock", title: store.search.isEmpty ? "No recent calls" : "No calls found",
                                   message: store.search.isEmpty ? "Your calls will appear here." : "Try another name or number.")
                        .listRowBackground(Color.clear)
                } else {
                    ForEach(store.visibleHistory) { record in
                        Button { store.recordDetail = record } label: { row(record) }
                            .buttonStyle(.plain)
                            .accessibilityElement(children: .combine)
                            .accessibilityHint("Shows call details")
                            .listRowBackground(Theme.backgroundSurface)
                            .listRowSeparatorTint(Theme.borderDecorative)
                    }
                    .onDelete { offsets in
                        let ids = Set(offsets.map { store.visibleHistory[$0].id })
                        store.removeHistory(ids)
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .environment(\.defaultMinListRowHeight, 60)
        .refreshable { await store.refresh() }
    }

    private func row(_ record: PhoneCallRecord) -> some View {
        let missed = record.outcome == .missed
        return PersonRow(person: record.person, nameColor: missed ? Theme.textDestructive : Theme.textPrimary,
                         trailing: friendlyDate(record.date)) {
            Label(callKind(record), systemImage: missed ? "phone.arrow.down.left" : record.direction == .incoming ? "phone.arrow.down.left" : "phone.arrow.up.right")
                .font(.callout).foregroundStyle(missed ? Theme.textDestructive : Theme.textSecondary)
            // Only an answered incoming call is ever checked, so only it carries a voice result.
            if record.direction == .incoming && record.outcome == .completed { VoiceBadge(voice: record.voice) }
        }
    }

    private func callKind(_ record: PhoneCallRecord) -> String {
        switch record.outcome {
        case .missed: return "Missed call"
        case .completed: return record.direction == .incoming ? "Incoming call" : "Outgoing call"
        case .cancelled: return "Cancelled call"
        case .failed: return "Call didn’t connect"
        case .answeredElsewhere: return "Answered on another device"
        }
    }
}

/// The calm, at-a-glance answer to "is Callshield watching my calls?" at the top of Recents.
struct ProtectionStatusCard: View {
    let active: Bool
    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: active ? "checkmark.shield.fill" : "shield.slash")
                .font(.system(size: 24, weight: .semibold))
                .foregroundStyle(active ? Theme.actionAccent : Theme.textSecondary)
                .frame(width: 48, height: 48)
                .background(active ? Theme.actionAccentBackground : Theme.backgroundPrimary, in: Circle())
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                Text(active ? "Voice checks are on" : "Voice checks are off")
                    .font(.headline).foregroundStyle(Theme.textPrimary)
                Text(active ? "Callshield listens for AI voices on incoming Callshield calls."
                            : "Calls still work through your mobile service.")
                    .font(.callout).foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .card(padding: 16)
        .accessibilityElement(children: .combine)
    }
}

struct ProductionFavoritesView: View {
    @EnvironmentObject private var store: ProductionStore
    var body: some View {
        ScrollView {
            if store.favorites.isEmpty {
                VStack(spacing: 8) {
                    EmptyStateView(symbol: "star", title: "No favorites", message: "Open a contact and tap Add to Favorites.")
                    Button("Open Contacts") { store.tab = .contacts }.buttonStyle(ActionButtonStyle(kind: .secondary))
                }.padding(.horizontal, Theme.margin)
            } else {
                GroupedRows {
                    ForEach(Array(store.favorites.enumerated()), id: \.element.id) { index, person in
                        if index > 0 { RowDivider(inset: 66) }
                        ProductionContactRow(person: person) { store.detail = person }
                    }
                }
                .padding(.horizontal, Theme.margin).padding(.bottom, 24)
            }
        }
    }
}

struct ProductionContactsView: View {
    @EnvironmentObject private var store: ProductionStore
    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                if store.contactsAccess == .notRequested || store.contactsAccess == .denied {
                    EmptyStateView(symbol: "person.crop.circle", title: "Your contacts",
                                   message: store.contactsAccess == .notRequested ? "Choose which contacts Callshield can use." : "Allow contacts in Settings, or dial a number with the keypad.")
                    Button(store.contactsAccess == .notRequested ? "Allow Contacts" : "Open Settings") {
                        if store.contactsAccess == .notRequested { Task { await store.allowContacts() } }
                        else { openAppSettings() }
                    }
                    .buttonStyle(ActionButtonStyle()).accessibilityIdentifier("allowContactsButton")
                } else {
                    PhoneSearchField(text: $store.contactSearch, label: "Search contacts", placeholder: "Search contacts")
                    if store.contactsAccess == .limited {
                        HStack {
                            Text("Showing selected contacts").font(.callout).foregroundStyle(Theme.textSecondary)
                            Spacer()
                            Button("Manage") { openAppSettings() }.font(.callout.weight(.semibold))
                                .frame(minHeight: 44).foregroundStyle(Theme.actionAccent)
                        }
                    }
                    if store.loadingContacts { ProgressView().controlSize(.large).padding(40) }
                    else if store.visibleContacts.isEmpty {
                        EmptyStateView(symbol: "person.2", title: "No contacts", message: "Contacts with phone numbers will appear here.")
                    } else {
                        GroupedRows {
                            ForEach(Array(store.visibleContacts.enumerated()), id: \.element.id) { index, person in
                                if index > 0 { RowDivider(inset: 66) }
                                ProductionContactRow(person: person) { store.detail = person }
                            }
                        }
                    }
                }
            }.padding(.horizontal, Theme.margin).padding(.bottom, 24)
        }.refreshable { await store.refreshContacts() }
    }
}

struct ProductionContactRow: View {
    let person: Person
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            PersonRow(person: person) {
                Text(person.number).font(.callout).foregroundStyle(Theme.textSecondary)
            }
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityHint("Shows contact details")
    }
}

struct ProductionKeypadView: View {
    @EnvironmentObject private var store: ProductionStore
    @FocusState private var editing: Bool
    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                TextField("Enter a number", text: $store.dialedNumber)
                    .font(.system(size: 34, weight: .medium)).multilineTextAlignment(.center)
                    .foregroundStyle(Theme.textPrimary)
                    .minimumScaleFactor(0.6)
                    .keyboardType(.phonePad).focused($editing)
                    .textContentType(.telephoneNumber).accessibilityIdentifier("productionNumber")
                    .frame(minHeight: 52)
                    .padding(.horizontal, Theme.margin).padding(.top, 4)
                if editing {
                    Button("Done") { editing = false }.font(.body.weight(.semibold)).frame(minHeight: 44)
                        .foregroundStyle(Theme.actionAccent)
                }
                PhoneKeypad { digit in editing = false; store.dialedNumber.append(digit) }
                HStack {
                    Button { editing = false; if store.dialedNumber.isEmpty { store.dialedNumber = "+" } } label: {
                        Image(systemName: "plus").font(.title2.weight(.semibold)).frame(width: 64, height: 64)
                    }.foregroundStyle(Theme.textSecondary).accessibilityLabel("International prefix")
                    Spacer()
                    Button { editing = false; Task { await store.call() } } label: {
                        Group {
                            if store.placingCall { ProgressView().tint(.white) }
                            else { Image(systemName: "phone.fill").font(.system(size: 32)) }
                        }
                        .foregroundStyle(.white).frame(width: 80, height: 80)
                        .background(Theme.actionAccept, in: Circle())
                        .opacity(store.dialedNumber.isEmpty ? 0.45 : 1)
                    }
                    .buttonStyle(.plain).disabled(store.dialedNumber.isEmpty || store.placingCall)
                    .accessibilityLabel("Call").accessibilityIdentifier("productionCallButton")
                    Spacer()
                    Button { if !store.dialedNumber.isEmpty { store.dialedNumber.removeLast() } } label: {
                        Image(systemName: "delete.left").font(.title2).frame(width: 64, height: 64)
                    }
                    .foregroundStyle(Theme.textSecondary).accessibilityLabel("Delete digit").accessibilityIdentifier("deleteDigit")
                    .contextMenu { Button("Clear number") { store.dialedNumber = "" } }
                }
                .frame(maxWidth: 300)
            }
            .frame(maxWidth: .infinity).padding(.bottom, 24)
        }
        .scrollDismissesKeyboard(.interactively)
        .toolbar { ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("Done") { editing = false } } }
    }
}

struct PhoneKeypad: View {
    let action: (String) -> Void
    private let digits = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"]
    private let letters = ["", "ABC", "DEF", "GHI", "JKL", "MNO", "PQRS", "TUV", "WXYZ", "", "+", ""]
    var body: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 20), count: 3), spacing: 16) {
            ForEach(Array(digits.enumerated()), id: \.offset) { index, digit in
                Button { action(digit) } label: {
                    VStack(spacing: 0) {
                        Text(digit).font(.system(size: 34, weight: .regular))
                        if !letters[index].isEmpty {
                            Text(letters[index]).font(.system(size: 12, weight: .semibold)).foregroundStyle(Theme.textSecondary)
                        }
                    }
                    .foregroundStyle(Theme.textPrimary).frame(width: 80, height: 80)
                    .background(Theme.backgroundSurface, in: Circle())
                    .overlay(Circle().strokeBorder(Theme.borderDecorative, lineWidth: 1))
                }
                .buttonStyle(.plain).accessibilityLabel(digit).accessibilityIdentifier("dialKey\(digit)")
            }
        }
        .frame(maxWidth: 300)
        .dynamicTypeSize(...DynamicTypeSize.xxLarge)
    }
}

struct ProductionPersonDetail: View {
    let person: Person
    var record: PhoneCallRecord?
    @EnvironmentObject private var store: ProductionStore
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    VStack(spacing: 8) {
                        Avatar(person: person, size: 88)
                        Text(person.name).font(.title.weight(.semibold)).foregroundStyle(Theme.textPrimary)
                            .multilineTextAlignment(.center).accessibilityAddTraits(.isHeader)
                        if !person.number.isEmpty {
                            Text(person.number).font(.title3).foregroundStyle(Theme.textSecondary)
                        }
                    }
                    // A caller who withheld their number has none: there is nothing to call back or to favourite
                    // (a person's id is their number, so every such caller would share one favourite).
                    if !person.number.isEmpty {
                        VStack(spacing: 12) {
                            Button { Task { await store.call(person) } } label: {
                                Label("Call \(person.name)", systemImage: "phone.fill")
                            }.buttonStyle(ActionButtonStyle(kind: .accept)).disabled(store.placingCall)
                            Button { store.toggleFavorite(person) } label: {
                                Label(store.isFavorite(person) ? "Remove from Favorites" : "Add to Favorites",
                                      systemImage: store.isFavorite(person) ? "star.fill" : "star")
                            }.buttonStyle(ActionButtonStyle(kind: .secondary))
                        }
                    }
                    if let record { recordDetails(record) }
                }
                .padding(Theme.margin)
            }
            .background(Theme.backgroundPrimary.ignoresSafeArea())
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }.font(.body.weight(.semibold))
                }
            }
        }
    }

    @ViewBuilder private func recordDetails(_ record: PhoneCallRecord) -> some View {
        let checked = record.direction == .incoming && record.outcome == .completed
        VoiceStatusCard(voice: record.voice, heading: "Voice check",
                        message: checked ? (record.deepfake?.historyMessage ?? record.voice.explanation)
                                         : "This call wasn’t checked. Only answered incoming calls are checked.") {
            if let assessment = record.deepfake {
                Text("Last voice update \(assessment.updatedAt.formatted(date: .abbreviated, time: .shortened))")
                    .font(.callout).foregroundStyle(Theme.textSecondary)
            }
        }
        if let transcript = record.transcript {
            VStack(alignment: .leading, spacing: 10) {
                Label("Scam-language check", systemImage: "text.bubble")
                    .font(.callout.weight(.semibold)).foregroundStyle(Theme.textSecondary)
                    .accessibilityAddTraits(.isHeader)
                Text(transcript.title).font(.title3.weight(.semibold))
                    .foregroundStyle(transcript.isWarning ? Theme.statusAI : Theme.textPrimary)
                Text(transcript.message).font(.body).foregroundStyle(Theme.textPrimary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .card()
        }
        SectionHeader(text: "Call information")
        GroupedRows {
            InfoRow(label: "Call type", value: record.direction.rawValue.capitalized)
            RowDivider()
            InfoRow(label: "Status", value: record.outcome == .answeredElsewhere ? "Answered elsewhere" : record.outcome.rawValue.capitalized)
            RowDivider()
            InfoRow(label: "Time", value: record.date.formatted(date: .abbreviated, time: .shortened))
            RowDivider()
            InfoRow(label: "Duration", value: callDuration(record.duration))
        }
        Footnote(text: "Voice labels do not verify who is calling or whether a call is safe.", symbol: "info.circle")
        Button(role: .destructive) { store.removeHistory([record.id]); dismiss() } label: {
            Label("Remove from Recents", systemImage: "trash")
        }
        .font(.body.weight(.semibold)).foregroundStyle(Theme.textDestructive).frame(minHeight: 52)
    }
}

struct ProductionSettingsView: View {
    @EnvironmentObject private var store: ProductionStore
    @AppStorage(AppearanceChoice.storageKey) private var appearance = AppearanceChoice.system
    /// An inbound-only backend (LiveKit) leaves outgoing calls to the mobile service, and no
    /// voice assessment reaches this phone for it, so only a full calling backend claims either.
    @MainActor private var callshieldPlacesCalls: Bool {
        store.coordinator.backend.isConfigured && store.coordinator.backend.canPlaceOutgoingCalls
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(spacing: 10) {
                    BrandMark()
                    Text("Callshield").font(.title2.weight(.semibold)).foregroundStyle(Theme.textPrimary)
                    Text("A little more clarity. Every call.").font(.body).foregroundStyle(Theme.textSecondary)
                }.frame(maxWidth: .infinity).padding(.vertical, 8)

                SectionHeader(text: "Display")
                DisplaySettings(largeText: $store.largeText, appearance: $appearance)

                SectionHeader(text: "Calling")
                GroupedRows {
                    InfoRow(label: "Calls go through", value: callshieldPlacesCalls ? "Callshield" : "Mobile service")
                    RowDivider()
                    InfoRow(label: "Voice checks", value: store.coordinator.backend.isConfigured ? "On incoming Callshield calls" : "Unavailable")
                }
                VStack(alignment: .leading, spacing: 12) {
                    Text("Default calling app").font(.headline).foregroundStyle(Theme.textPrimary)
                    Text("To choose Callshield where supported, open iPhone Settings → Apps → Default Apps.")
                        .font(.body).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
                    Button("Open iPhone Settings") { openAppSettings() }.buttonStyle(ActionButtonStyle(kind: .secondary))
                }
                .card()

                SectionHeader(text: "Understanding voice labels")
                VoiceLabelGuide()

                Footnote(text: "Favorites and Callshield call history are stored on this iPhone. Contacts are accessed only with your permission.",
                         symbol: "lock.fill")
            }.padding(.horizontal, Theme.margin).padding(.bottom, 32)
        }
    }
}

/// Larger text and appearance, shared by the production and demo Settings screens.
struct DisplaySettings: View {
    @Binding var largeText: Bool
    @Binding var appearance: AppearanceChoice
    var toggleID = "largerTextToggle"
    var body: some View {
        GroupedRows {
            Toggle(isOn: $largeText) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Larger text").font(.body.weight(.medium)).foregroundStyle(Theme.textPrimary)
                    Text("Makes words bigger across the app.").font(.callout).foregroundStyle(Theme.textSecondary)
                }
            }
            .tint(Theme.actionAccent).padding(.vertical, 12).frame(minHeight: 64)
            .accessibilityIdentifier(toggleID)
            RowDivider()
            VStack(alignment: .leading, spacing: 10) {
                Text("Appearance").font(.body.weight(.medium)).foregroundStyle(Theme.textPrimary)
                ChoiceBar(options: AppearanceChoice.allCases.map { (value: $0, title: $0.rawValue, accessibility: "\($0.rawValue) appearance") },
                          selection: $appearance, identifier: { "appearance\($0.rawValue)" })
            }
            .padding(.vertical, 14)
        }
    }
}

/// Every voice label with its icon, colors and a plain-language meaning.
struct VoiceLabelGuide: View {
    var body: some View {
        GroupedRows {
            ForEach(Array([Voice.ai, .human, .unknown].enumerated()), id: \.element) { index, voice in
                if index > 0 { RowDivider() }
                VStack(alignment: .leading, spacing: 8) {
                    VoiceBadge(voice: voice)
                    Text(voice.explanation).font(.body).foregroundStyle(Theme.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.vertical, 14)
            }
        }
    }
}

func openAppSettings() {
    guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
    UIApplication.shared.open(url)
}
