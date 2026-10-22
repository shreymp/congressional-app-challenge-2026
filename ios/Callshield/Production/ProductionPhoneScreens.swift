import SwiftUI
import UIKit

struct ProductionRecentsView: View {
    @EnvironmentObject private var store: ProductionStore
    var body: some View {
        VStack(spacing: 0) {
            Picker("Filter calls", selection: $store.filter) {
                ForEach(CallFilter.allCases, id: \.self) { Text($0.rawValue).tag($0) }
            }.pickerStyle(.segmented).padding(.horizontal, 23).padding(.bottom, 14)
            PhoneSearchField(text: $store.search, label: "Search recent calls").padding(.horizontal, 23)
            if store.visibleHistory.isEmpty {
                ScrollView {
                    PhoneEmptyView(symbol: "clock", title: store.search.isEmpty ? "No recent calls" : "No calls found",
                                   message: store.search.isEmpty ? "Your calls will appear here." : "Try another name or number.")
                }
            } else {
                List {
                    ForEach(store.visibleHistory) { record in
                        Button { store.recordDetail = record } label: {
                            HStack(spacing: 10) {
                                Avatar(person: record.person)
                                VStack(alignment: .leading, spacing: 5) {
                                    Text(record.person.name).font(store.largeText ? .headline : .subheadline.weight(.semibold))
                                        .foregroundStyle(record.outcome == .missed ? Palette.missed : Palette.ink)
                                    HStack {
                                        Image(systemName: record.direction == .incoming ? "arrow.down.left" : "arrow.up.right")
                                        Text(record.outcome == .missed ? "Missed" : record.direction.rawValue.capitalized)
                                        VoiceBadge(voice: record.voice)
                                    }.font(.caption2).foregroundStyle(Palette.secondary)
                                }
                                Spacer()
                                Text(record.date, format: .dateTime.month(.abbreviated).day()).font(.caption2).foregroundStyle(Palette.secondary)
                                Image(systemName: "info.circle").foregroundStyle(Color(hex: 0x528FCB))
                            }.padding(.vertical, 5)
                        }.buttonStyle(.plain)
                    }
                    .onDelete { offsets in
                        let ids = Set(offsets.map { store.visibleHistory[$0].id })
                        store.removeHistory(ids)
                    }
                }.listStyle(.plain).scrollContentBackground(.hidden)
            }
        }
        .refreshable { await store.refresh() }
    }
}

struct ProductionFavoritesView: View {
    @EnvironmentObject private var store: ProductionStore
    var body: some View {
        ScrollView {
            if store.favorites.isEmpty {
                PhoneEmptyView(symbol: "star", title: "No favorites", message: "Open a contact and tap Add to Favorites.")
                Button("Open Contacts") { store.tab = .contacts }.tint(Palette.accent)
            } else {
                LazyVStack(spacing: 0) {
                    ForEach(store.favorites) { person in
                        ProductionContactRow(person: person) { store.detail = person }
                    }
                }.padding(.horizontal, 23)
            }
        }
    }
}

struct ProductionContactsView: View {
    @EnvironmentObject private var store: ProductionStore
    @State private var showGuardianSetup = false
    @State private var guardianToRemove: TrustedGuardian?
    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                guardianCard.padding(.bottom, 18)
                if store.contactsAccess == .notRequested || store.contactsAccess == .denied {
                    PhoneEmptyView(symbol: "person.crop.circle", title: "Your contacts",
                                   message: store.contactsAccess == .notRequested ? "Choose which contacts callma. can use." : "Allow contacts in Settings, or dial a number with the keypad.")
                    Button(store.contactsAccess == .notRequested ? "Allow Contacts" : "Open Settings") {
                        if store.contactsAccess == .notRequested { Task { await store.allowContacts() } }
                        else { openAppSettings() }
                    }
                    .buttonStyle(.borderedProminent).tint(Palette.accent).accessibilityIdentifier("allowContactsButton")
                } else {
                    PhoneSearchField(text: $store.contactSearch, label: "Search contacts").padding(.bottom, 14)
                    if store.contactsAccess == .limited {
                        HStack {
                            Text("Showing selected contacts").font(.caption).foregroundStyle(Palette.secondary)
                            Spacer()
                            Button("Manage") { openAppSettings() }.font(.caption).tint(Palette.accent)
                        }.padding(.bottom, 12)
                    }
                    if store.loadingContacts { ProgressView().padding(40) }
                    else if store.visibleContacts.isEmpty {
                        PhoneEmptyView(symbol: "person.2", title: "No contacts", message: "Contacts with phone numbers will appear here.")
                    } else {
                        LazyVStack(spacing: 0) {
                            ForEach(store.visibleContacts) { person in
                                ProductionContactRow(person: person) { store.detail = person }
                            }
                        }
                    }
                }
            }.padding(.horizontal, 23)
        }.refreshable { await store.refreshContacts() }
        .sheet(isPresented: $showGuardianSetup) { GuardianSetupSheet(store: store) }
        .confirmationDialog("Remove this trusted guardian?", isPresented: Binding(get: { guardianToRemove != nil }, set: { if !$0 { guardianToRemove = nil } })) {
            Button("Remove Guardian", role: .destructive) { if let guardianToRemove { store.removeGuardian(guardianToRemove) } }
            Button("Cancel", role: .cancel) { guardianToRemove = nil }
        }
    }
    private var guardianCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Trusted Guardians", systemImage: "person.2.fill").font(.headline)
            ForEach(store.guardians) { guardian in
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(guardian.name).font(.subheadline.weight(.semibold))
                        Text(guardian.number).font(.caption).foregroundStyle(Palette.secondary)
                    }
                    Spacer()
                    Button { guardianToRemove = guardian } label: { Image(systemName: "minus.circle").frame(width: 44, height: 44) }
                        .accessibilityLabel("Remove guardian \(guardian.name)")
                }
            }
            Button { showGuardianSetup = true } label: { Label("Add Trusted Guardian", systemImage: "person.badge.plus").frame(minHeight: 44) }
                .accessibilityIdentifier("addTrustedGuardian")
            Text("Choose family or friends who can check in. You review every message before sending.")
                .font(.caption).foregroundStyle(Palette.secondary)
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(Palette.softAccent, in: RoundedRectangle(cornerRadius: 12))
        .foregroundStyle(Palette.ink).tint(Palette.accent)
    }
}

struct ProductionContactRow: View {
    let person: Person
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 13) {
                Avatar(person: person)
                VStack(alignment: .leading, spacing: 5) {
                    Text(person.name).font(.subheadline.weight(.semibold)).foregroundStyle(Palette.ink)
                    Text(person.number).font(.caption).foregroundStyle(Palette.secondary)
                }
                Spacer()
                Image(systemName: "chevron.right").foregroundStyle(Palette.secondary)
            }.padding(.vertical, 16).contentShape(Rectangle())
        }.buttonStyle(.plain)
    }
}

struct PhoneSearchField: View {
    @Binding var text: String
    let label: String
    var body: some View {
        HStack(spacing: 7) {
            Image(systemName: "magnifyingglass").foregroundStyle(Palette.secondary)
            TextField("Search", text: $text).textInputAutocapitalization(.never).autocorrectionDisabled()
                .accessibilityLabel(label)
            if !text.isEmpty {
                Button { text = "" } label: { Image(systemName: "xmark.circle.fill") }
                    .foregroundStyle(Palette.secondary).accessibilityLabel("Clear search")
            }
        }.padding(10).background(Palette.softAccent, in: RoundedRectangle(cornerRadius: 10))
    }
}

struct ProductionKeypadView: View {
    @EnvironmentObject private var store: ProductionStore
    @FocusState private var editing: Bool
    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                TextField("Enter a number", text: $store.dialedNumber)
                    .scaledFont(size: 30, weight: .regular).multilineTextAlignment(.center)
                    .keyboardType(.phonePad).focused($editing)
                    .textContentType(.telephoneNumber).accessibilityIdentifier("productionNumber")
                    .padding(.horizontal, 15).padding(.top, 12)
                if editing { Button("Done") { editing = false }.tint(Palette.accent) }
                PhoneKeypad { digit in editing = false; store.dialedNumber.append(digit) }
                HStack {
                    Button { editing = false; if store.dialedNumber.isEmpty { store.dialedNumber = "+" } } label: {
                        Image(systemName: "plus").frame(width: 60, height: 60)
                    }.foregroundStyle(Palette.secondary).accessibilityLabel("International prefix")
                    Spacer()
                    Button { editing = false; Task { await store.call() } } label: {
                        Group {
                            if store.placingCall { ProgressView().tint(.white) }
                            else { Image(systemName: "phone.fill").scaledFont(size: 29) }
                        }
                        .foregroundStyle(.white).frame(width: 70, height: 70)
                        .background(Palette.teal, in: Circle())
                    }
                    .buttonStyle(.plain).disabled(store.dialedNumber.isEmpty || store.placingCall)
                    .accessibilityLabel("Call").accessibilityIdentifier("productionCallButton")
                    Spacer()
                    Button { if !store.dialedNumber.isEmpty { store.dialedNumber.removeLast() } } label: {
                        Image(systemName: "delete.left").scaledFont(size: 23).frame(width: 60, height: 60)
                    }
                    .foregroundStyle(Palette.secondary).accessibilityLabel("Delete digit").accessibilityIdentifier("deleteDigit")
                    .contextMenu { Button("Clear number") { store.dialedNumber = "" } }
                }
                .frame(maxWidth: 290)
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
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 24), count: 3), spacing: 15) {
            ForEach(Array(digits.enumerated()), id: \.offset) { index, digit in
                Button { action(digit) } label: {
                    VStack(spacing: 0) {
                        Text(digit).scaledFont(size: 31, weight: .regular)
                        Text(letters[index]).scaledFont(size: 9, weight: .semibold).tracking(1.4)
                    }
                    .foregroundStyle(Palette.ink).frame(width: 74, height: 74)
                    .background(Palette.softAccent, in: Circle())
                }
                .buttonStyle(.plain).accessibilityLabel(digit).accessibilityIdentifier("dialKey\(digit)")
            }
        }.frame(maxWidth: 290)
    }
}

struct ProductionPersonDetail: View {
    let person: Person
    var record: PhoneCallRecord?
    @EnvironmentObject private var store: ProductionStore
    @Environment(\.dismiss) private var dismiss
    @State private var showBlockConfirmation = false
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    Avatar(person: person, size: 80)
                    Text(person.name).font(.title2.weight(.semibold))
                    // A caller who withheld their number has none: there is nothing to call back or to favourite
                    // (a person's id is their number, so every such caller would share one favourite).
                    if !person.number.isEmpty {
                        Text(person.number).font(.body).foregroundStyle(Palette.secondary)
                        Button { Task { await store.call(person) } } label: {
                            Label("Call", systemImage: "phone.fill").frame(maxWidth: .infinity, minHeight: 44)
                        }.buttonStyle(.borderedProminent).tint(Palette.accent).disabled(store.placingCall)
                        Button { store.toggleFavorite(person) } label: {
                            Label(store.isFavorite(person) ? "Remove from Favorites" : "Add to Favorites", systemImage: store.isFavorite(person) ? "star.fill" : "star")
                        }.tint(Palette.accent)
                    }
                    if !person.number.isEmpty {
                        if store.isGuardian(person) {
                            Label("Trusted Guardian", systemImage: "person.crop.circle.badge.checkmark").foregroundStyle(Palette.accent)
                        } else {
                            Button { do { try store.addGuardian(name: person.name, number: person.number) } catch { store.safetyStatus = error.localizedDescription } }
                                label: { Label("Add as Trusted Guardian", systemImage: "person.badge.plus") }
                                .frame(minHeight: 44)
                        }
                    }
                    if let record {
                        VoiceBadge(voice: record.voice, size: 12)
                        if let assessment = record.deepfake {
                            Text(assessment.historyMessage).font(.caption).foregroundStyle(Palette.secondary)
                        }
                        if let transcript = record.transcript {
                            Text("Transcript analysis").font(.subheadline.weight(.semibold))
                            Text(transcript.title).font(.caption)
                            Text(transcript.message).font(.caption).foregroundStyle(Palette.secondary)
                            if let excerpt = transcript.savedExcerpt, transcript.isWarning {
                                Text("Saved caller transcript excerpt").font(.headline)
                                Text(excerpt).font(.body).textSelection(.enabled)
                                Text("Automatic transcript; words may be missing or incorrect.")
                                    .font(.caption).foregroundStyle(Palette.secondary)
                            }
                        }
                        VStack(spacing: 12) {
                            detailRow("Call type", record.direction.rawValue.capitalized)
                            detailRow("Status", record.outcome.rawValue.capitalized)
                            detailRow("Time", record.date.formatted())
                            detailRow("Duration", callDuration(record.duration))
                        }.padding(16).background(Palette.softAccent, in: RoundedRectangle(cornerRadius: 12))
                        Text("Voice labels do not verify caller identity or safety.").font(.footnote).foregroundStyle(Palette.secondary)
                        if !person.number.isEmpty {
                            if let block = store.blockedNumbers.first(where: { SafetyNumber.matches($0.number, person.number) }) {
                                Label("You Blocked This Number", systemImage: "hand.raised.fill").font(.headline)
                                Text(block.serverSynced ? "Blocked for your callma. calls." : "Blocked in this app on this iPhone. Server sync is pending.").font(.footnote).foregroundStyle(.secondary)
                                Button("Unblock Number") { Task { await store.unblock(block) } }.frame(minHeight: 44).disabled(store.syncingSafety)
                            } else {
                                Button("Block or Report Number", role: .destructive) { showBlockConfirmation = true }
                                    .frame(minHeight: 44).accessibilityIdentifier("blockOrReportNumber")
                                    .disabled(store.syncingSafety)
                            }
                            Text("Blocking is your choice after a call. Reports are reviewed before a number can be blocked for everyone.").font(.footnote).foregroundStyle(.secondary)
                        }
                    }
                    if let status = store.safetyStatus { Text(status).font(.footnote).foregroundStyle(.secondary).accessibilityIdentifier("safetyStatus") }
                }.padding(23)
            }
            .navigationTitle("Call Details").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .confirmationDialog("Block or report this number?", isPresented: $showBlockConfirmation, titleVisibility: .visible) {
                Button("Block and Report", role: .destructive) { Task { await store.blockAfterCall(person, report: true) } }
                Button("Block for Me", role: .destructive) { Task { await store.blockAfterCall(person, report: false) } }
                Button("Report for Review") { Task { await store.reportAfterCall(person) } }
                Button("Cancel", role: .cancel) {}
            } message: { Text("Caller ID can be spoofed. Personal blocks apply to callma. calls; reports are reviewed for the community list.") }
        }
    }
    private func detailRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) { Text(label).foregroundStyle(Palette.secondary); Spacer(); Text(value).multilineTextAlignment(.trailing) }.font(.subheadline)
    }
}

struct ProductionSettingsView: View {
    @EnvironmentObject private var store: ProductionStore
    @State private var showingBlockedNumbers = false
    /// An inbound-only backend (LiveKit) leaves outgoing calls to the mobile service, and no
    /// voice assessment reaches this phone for it, so only a full calling backend claims either.
    @MainActor private var callshieldPlacesCalls: Bool {
        store.coordinator.backend.isConfigured && store.coordinator.backend.canPlaceOutgoingCalls
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(spacing: 12) {
                    BrandMark()
                    Text(AppBrand.name).font(.title3.weight(.semibold))
                    Text(AppBrand.tagline).font(.caption).foregroundStyle(Palette.secondary)
                }.frame(maxWidth: .infinity).padding(20)
                    .background(LinearGradient(colors: [Palette.softAccent, Palette.lavender, Palette.sand], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 24))
                VStack(spacing: 0) {
                    Toggle("Larger text", isOn: $store.largeText).tint(Palette.accent).padding(.vertical, 12)
                    Divider()
                    row("Calling", callshieldPlacesCalls ? "callma." : "Mobile service")
                    Divider()
                    row("Voice labels", store.coordinator.backend.isConfigured ? "On incoming callma. calls" : "Unavailable")
                }.padding(.horizontal, 16).background(Palette.softAccent, in: RoundedRectangle(cornerRadius: 12))
                VStack(alignment: .leading, spacing: 12) {
                    Text("Safety").font(.headline)
                    Button { showingBlockedNumbers = true } label: { Label("Blocked Numbers", systemImage: "hand.raised").frame(minHeight: 44) }
                        .accessibilityIdentifier("blockedNumbersButton")
                    Button { store.tab = .contacts } label: { Label("Manage Trusted Guardians", systemImage: "person.2").frame(minHeight: 44) }
                    row("Blocking service", store.safetyBackend.isConfigured ? "Connected" : "Not configured")
                    Text("Detection checks are experimental. No number is automatically blocked because of a score.").font(.caption).foregroundStyle(Palette.secondary)
                }.padding(16).background(Palette.softAccent, in: RoundedRectangle(cornerRadius: 12))
                VStack(alignment: .leading, spacing: 10) {
                    Text("Default calling app").font(.headline)
                    Text("To choose callma. where supported, open iPhone Settings → Apps → Default Apps.")
                        .font(.subheadline).foregroundStyle(Palette.secondary)
                    Button("Open Settings") { openAppSettings() }.tint(Palette.accent)
                }
                Text("Voice checks can be wrong. If a caller asks for money, passwords, or a security code, hang up and call someone you trust.")
                    .font(.subheadline).foregroundStyle(Palette.secondary)
                Text("Guardians, personal blocks, favorites, and callma. history are saved on this iPhone. Contacts require your permission. A connected blocking service receives numbers you manually block or report, but no transcript.")
                    .font(.caption).foregroundStyle(Palette.secondary)
                Text("Guardian messages are sent only after you review and send them. Transcript excerpts may contain private information and recognition errors.")
                    .font(.caption).foregroundStyle(Palette.secondary)
                Text("callma. blocks apply to calls handled by callma.; they do not block unrelated calls in the Phone app.")
                    .font(.caption).foregroundStyle(Palette.secondary)
            }.padding(.horizontal, 23).padding(.bottom, 24)
        }
        .sheet(isPresented: $showingBlockedNumbers) {
            NavigationStack {
                BlockedNumbersView(store: store)
                    .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { showingBlockedNumbers = false } } }
            }
        }
    }
    private func row(_ label: String, _ value: String) -> some View {
        HStack { Text(label); Spacer(); Text(value).foregroundStyle(Palette.secondary) }.font(.subheadline).padding(.vertical, 14)
    }
}

func openAppSettings() {
    guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
    UIApplication.shared.open(url)
}

