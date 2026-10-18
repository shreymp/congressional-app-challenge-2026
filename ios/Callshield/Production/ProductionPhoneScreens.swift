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
                }.listStyle(.plain)
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
                Button("Open Contacts") { store.tab = .contacts }.tint(Palette.green)
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
    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                if store.contactsAccess == .notRequested || store.contactsAccess == .denied {
                    PhoneEmptyView(symbol: "person.crop.circle", title: "Your contacts",
                                   message: store.contactsAccess == .notRequested ? "Choose which contacts Callshield can use." : "Allow contacts in Settings, or dial a number with the keypad.")
                    Button(store.contactsAccess == .notRequested ? "Allow Contacts" : "Open Settings") {
                        if store.contactsAccess == .notRequested { Task { await store.allowContacts() } }
                        else { openAppSettings() }
                    }
                    .buttonStyle(.borderedProminent).tint(Palette.green).accessibilityIdentifier("allowContactsButton")
                } else {
                    PhoneSearchField(text: $store.contactSearch, label: "Search contacts").padding(.bottom, 14)
                    if store.contactsAccess == .limited {
                        HStack {
                            Text("Showing selected contacts").font(.caption).foregroundStyle(Palette.secondary)
                            Spacer()
                            Button("Manage") { openAppSettings() }.font(.caption).tint(Palette.green)
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
                .overlay(alignment: .bottom) { Divider() }
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
        }.padding(10).background(Color(hex: 0xF0F0F2), in: RoundedRectangle(cornerRadius: 10))
    }
}

struct ProductionKeypadView: View {
    @EnvironmentObject private var store: ProductionStore
    @FocusState private var editing: Bool
    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                TextField("Enter a number", text: $store.dialedNumber)
                    .font(.system(size: 30, weight: .regular)).multilineTextAlignment(.center)
                    .keyboardType(.phonePad).focused($editing)
                    .textContentType(.telephoneNumber).accessibilityIdentifier("productionNumber")
                    .padding(.horizontal, 15).padding(.top, 12)
                if editing { Button("Done") { editing = false }.tint(Palette.green) }
                PhoneKeypad { digit in editing = false; store.dialedNumber.append(digit) }
                HStack {
                    Button { editing = false; if store.dialedNumber.isEmpty { store.dialedNumber = "+" } } label: {
                        Image(systemName: "plus").frame(width: 60, height: 60)
                    }.foregroundStyle(Palette.secondary).accessibilityLabel("International prefix")
                    Spacer()
                    Button { editing = false; Task { await store.call() } } label: {
                        Group {
                            if store.placingCall { ProgressView().tint(.white) }
                            else { Image(systemName: "phone.fill").font(.system(size: 29)) }
                        }
                        .foregroundStyle(.white).frame(width: 70, height: 70)
                        .background(Color(hex: 0x32C968), in: Circle())
                    }
                    .buttonStyle(.plain).disabled(store.dialedNumber.isEmpty || store.placingCall)
                    .accessibilityLabel("Call").accessibilityIdentifier("productionCallButton")
                    Spacer()
                    Button { if !store.dialedNumber.isEmpty { store.dialedNumber.removeLast() } } label: {
                        Image(systemName: "delete.left").font(.system(size: 23)).frame(width: 60, height: 60)
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
                        Text(digit).font(.system(size: 31, weight: .regular))
                        Text(letters[index]).font(.system(size: 9, weight: .semibold)).tracking(1.4)
                    }
                    .foregroundStyle(Palette.ink).frame(width: 74, height: 74)
                    .background(Color(hex: 0xF0F0F2), in: Circle())
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
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    Avatar(person: person, size: 80)
                    Text(person.name).font(.title2.weight(.semibold))
                    Text(person.number).font(.body).foregroundStyle(Palette.secondary)
                    Button { Task { await store.call(person) } } label: {
                        Label("Call", systemImage: "phone.fill").frame(maxWidth: .infinity, minHeight: 36)
                    }.buttonStyle(.borderedProminent).tint(Palette.green).disabled(store.placingCall)
                    Button { store.toggleFavorite(person) } label: {
                        Label(store.isFavorite(person) ? "Remove from Favorites" : "Add to Favorites", systemImage: store.isFavorite(person) ? "star.fill" : "star")
                    }.tint(Palette.green)
                    if let record {
                        VoiceBadge(voice: record.voice, size: 12)
                        VStack(spacing: 12) {
                            detailRow("Call type", record.direction.rawValue.capitalized)
                            detailRow("Status", record.outcome.rawValue.capitalized)
                            detailRow("Time", record.date.formatted())
                            detailRow("Duration", callDuration(record.duration))
                        }.padding(16).background(Color(hex: 0xF5F7F5), in: RoundedRectangle(cornerRadius: 12))
                        Text("Voice labels do not verify caller identity or safety.").font(.caption).foregroundStyle(Palette.secondary)
                    }
                }.padding(23)
            }
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }.preferredColorScheme(.light)
    }
    private func detailRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) { Text(label).foregroundStyle(Palette.secondary); Spacer(); Text(value).multilineTextAlignment(.trailing) }.font(.subheadline)
    }
}

struct ProductionSettingsView: View {
    @EnvironmentObject private var store: ProductionStore
    @State private var server = UserDefaults.standard.string(forKey: "callshield.serverURL") ?? ""
    @State private var sessionToken = ""
    @State private var connectionMessage = ""
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(spacing: 12) {
                    BrandMark()
                    Text("Callshield").font(.title3.weight(.semibold))
                    Text("A little more clarity. Every call.").font(.caption).foregroundStyle(Palette.secondary)
                }.frame(maxWidth: .infinity)
                VStack(spacing: 0) {
                    Toggle("Larger text", isOn: $store.largeText).tint(Palette.green).padding(.vertical, 12)
                    Divider()
                    row("Calling", store.coordinator.backend.isConfigured ? "Callshield" : "Mobile service")
                    Divider()
                    row("Voice labels", store.coordinator.backend.isConfigured ? "During connected calls" : "Unavailable")
                }.padding(.horizontal, 16).background(Color(hex: 0xF6F7F6), in: RoundedRectangle(cornerRadius: 12))
                VStack(alignment: .leading, spacing: 10) {
                    Text("Transcript protection").font(.headline)
                    Text("Caller speech is transcribed and checked on this device. Live analysis needs a Callshield audio connection.")
                        .font(.subheadline).foregroundStyle(Palette.secondary)
                    Picker("Live transcript model", selection: Binding(get: { store.coordinator.transcript.model }, set: { model in
                        store.coordinator.transcript.select(model)
                        UserDefaults.standard.set(model.rawValue, forKey: "callshield.transcriptModel")
                    })) {
                        ForEach(TranscriptPipeline.Model.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                    }.pickerStyle(.menu).accessibilityIdentifier("liveTranscriptModel")
                    #if DEBUG
                    Button("Test transcript pipeline") { store.showTranscriptTester = true }
                        .accessibilityIdentifier("transcriptTestButton")
                    #endif
                }
                VStack(alignment: .leading, spacing: 10) {
                    Text("Calling connection").font(.headline)
                    TextField("https://your-callshield-server", text: $server)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .textFieldStyle(.roundedBorder)
                    SecureField("Server-issued session token", text: $sessionToken)
                        .textInputAutocapitalization(.never).autocorrectionDisabled().textFieldStyle(.roundedBorder)
                    HStack {
                        Button("Save connection") {
                            do {
                                try CallingConnection.save(server: server, token: sessionToken)
                                try store.reloadCallingConnection()
                                sessionToken = ""; connectionMessage = "Connection saved. Live calls require the server’s Twilio configuration."
                            } catch { store.errorMessage = error.localizedDescription }
                        }
                        Button("Disconnect") {
                            CallingConnection.clear()
                            do { try store.reloadCallingConnection(); server = ""; sessionToken = ""; connectionMessage = "Disconnected." }
                            catch { store.errorMessage = error.localizedDescription }
                        }
                    }
                    if !connectionMessage.isEmpty { Text(connectionMessage).font(.caption) }
                    Text("Use the session token from your calling server. It is saved in this iPhone’s Keychain.")
                        .font(.caption).foregroundStyle(Palette.secondary)
                }
                VStack(alignment: .leading, spacing: 10) {
                    Text("Default calling app").font(.headline)
                    Text("To choose Callshield where supported, open iPhone Settings → Apps → Default Apps.")
                        .font(.subheadline).foregroundStyle(Palette.secondary)
                    Button("Open Settings") { openAppSettings() }.tint(Palette.green)
                }
                VStack(alignment: .leading, spacing: 14) {
                    Text("Understanding voice labels").font(.headline)
                    ForEach([Voice.ai, .human, .unknown], id: \.self) { voice in
                        VStack(alignment: .leading, spacing: 7) {
                            VoiceBadge(voice: voice, size: 12)
                            Text(voice.explanation).font(.caption).foregroundStyle(Palette.secondary)
                        }
                    }
                }
                Text("Favorites and Callshield call history are stored on this iPhone. Contacts are accessed only with your permission.")
                    .font(.caption).foregroundStyle(Palette.secondary)
            }.padding(.horizontal, 23).padding(.bottom, 24)
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
