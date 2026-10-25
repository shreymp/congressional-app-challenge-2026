import SwiftUI
import MessageUI

struct GuardianSetupSheet: View {
    @ObservedObject var store: ProductionStore
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var number = ""
    @State private var error: String?
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Name", text: $name).textContentType(.name).accessibilityIdentifier("guardianName")
                    TextField("Phone Number", text: $number).keyboardType(.phonePad).textContentType(.telephoneNumber)
                        .accessibilityIdentifier("guardianNumber")
                } header: { Text("Trusted Guardian") } footer: {
                    Text("Choose someone you know who agrees to check in. Adding them does not send a message or share your calls. Include the country code, such as +1.")
                }
                if !store.contacts.isEmpty {
                    Section("Choose a Contact") {
                        ForEach(store.contacts) { person in
                            Button {
                                name = person.name; number = person.number
                            } label: { VStack(alignment: .leading) { Text(person.name); Text(person.number).font(.caption).foregroundStyle(.secondary) } }
                                .frame(minHeight: 44)
                        }
                    }
                }
                if let error { Text(error).foregroundStyle(.red).accessibilityIdentifier("guardianValidationError") }
            }
            .navigationTitle("Add Guardian").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        do { try store.addGuardian(name: name, number: number); dismiss() }
                        catch { self.error = error.localizedDescription }
                    }.disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || number.isEmpty)
                        .accessibilityIdentifier("saveGuardian")
                }
            }
        }.presentationDragIndicator(.visible)
    }
}

struct GuardianAlertSheet: View {
    let call: PhoneCall
    @ObservedObject var store: ProductionStore
    @Environment(\.dismiss) private var dismiss
    @State private var selectedID: UUID?
    @State private var includeExcerpt = false
    @State private var showSetup = false
    @State private var showComposer = false
    @State private var status: String?
    private var guardian: TrustedGuardian? { store.guardians.first { $0.id == selectedID } }
    private var draft: String { GuardianMessage.draft(call: call, includeExcerpt: includeExcerpt) }
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Ask someone you trust to check in. You choose the recipient and review the message before sending.")
                }
                if store.guardians.isEmpty {
                    Section {
                        Label("No trusted guardians yet", systemImage: "person.badge.plus")
                        Button("Add a Guardian") { showSetup = true }.frame(minHeight: 44)
                    }
                } else {
                    Section("Send To") {
                        ForEach(store.guardians) { person in
                            Button { selectedID = person.id } label: {
                                HStack {
                                    VStack(alignment: .leading) { Text(person.name); Text(person.number).font(.caption).foregroundStyle(.secondary) }
                                    Spacer()
                                    if selectedID == person.id { Image(systemName: "checkmark").accessibilityLabel("Selected") }
                                }.frame(minHeight: 44).contentShape(Rectangle())
                            }.foregroundStyle(.primary)
                        }
                    }
                }
                Section {
                    Toggle("Include Caller Transcript Excerpt", isOn: $includeExcerpt)
                        .disabled(call.transcript?.savedExcerpt?.isEmpty != false)
                    if call.transcript?.savedExcerpt?.isEmpty != false {
                        Text("No transcript excerpt is available. You can still send a check-in request.").font(.footnote).foregroundStyle(.secondary)
                    }
                } footer: { Text("Excerpts may contain private information or recognition errors. Only share them with someone you trust.") }
                Section("Message Preview") {
                    Text(draft).textSelection(.enabled).accessibilityIdentifier("guardianMessagePreview")
                    if MFMessageComposeViewController.canSendText() {
                        Button { showComposer = true } label: { Label("Review in Messages", systemImage: "message.fill") }
                            .disabled(guardian == nil).frame(minHeight: 44).accessibilityIdentifier("reviewGuardianMessage")
                    } else {
                        ShareLink(item: draft) { Label("Share Check-In Request", systemImage: "square.and.arrow.up") }
                            .frame(minHeight: 44)
                        Text("Messages is unavailable here. Choose your guardian in the sharing app.").font(.footnote).foregroundStyle(.secondary)
                    }
                    if let status { Text(status).font(.footnote).foregroundStyle(.secondary) }
                }
            }
            .navigationTitle("Contact a Guardian").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } } }
            .onAppear { selectedID = selectedID ?? store.guardians.first?.id }
            .sheet(isPresented: $showSetup, onDismiss: { selectedID = selectedID ?? store.guardians.first?.id }) { GuardianSetupSheet(store: store) }
            .sheet(isPresented: $showComposer) {
                if let guardian {
                    GuardianMessageComposer(number: guardian.number, messageBody: draft) { result in
                        showComposer = false
                        switch result {
                        case .sent: status = "Message sent to Messages. Delivery is not confirmed."
                        case .cancelled: status = "Message cancelled. Nothing was sent."
                        default: status = "The message couldn’t be sent. You can try again."
                        }
                    }
                }
            }
        }.presentationDragIndicator(.visible)
    }
}

private struct GuardianMessageComposer: UIViewControllerRepresentable {
    let number: String
    let messageBody: String
    let completion: (MessageComposeResult) -> Void
    func makeCoordinator() -> Coordinator { Coordinator(completion: completion) }
    func makeUIViewController(context: Context) -> MFMessageComposeViewController {
        let controller = MFMessageComposeViewController()
        controller.recipients = [number]; controller.body = messageBody; controller.messageComposeDelegate = context.coordinator
        return controller
    }
    func updateUIViewController(_ controller: MFMessageComposeViewController, context: Context) {}
    final class Coordinator: NSObject, MFMessageComposeViewControllerDelegate {
        let completion: (MessageComposeResult) -> Void
        init(completion: @escaping (MessageComposeResult) -> Void) { self.completion = completion }
        func messageComposeViewController(_ controller: MFMessageComposeViewController, didFinishWith result: MessageComposeResult) { completion(result) }
    }
}

struct BlockedNumbersView: View {
    @ObservedObject var store: ProductionStore
    var body: some View {
        List {
            Section {
                Text("Only numbers you manually block are added to your personal list. callma. never blocks a number because of a detection score.")
            }
            Section("Your Blocked Numbers") {
                if store.blockedNumbers.isEmpty { Text("No blocked numbers").foregroundStyle(.secondary) }
                ForEach(store.blockedNumbers) { block in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(block.name).font(.headline)
                        Text(block.number).font(.body)
                        Text(block.serverSynced ? "Synced to your callma. calling service" : "On this iPhone only · server sync pending")
                            .font(.footnote).foregroundStyle(.secondary)
                        Button("Unblock", role: .destructive) { Task { await store.unblock(block) } }.frame(minHeight: 44)
                            .disabled(store.syncingSafety)
                    }
                }
            }
            Section("Reviewed Community Blocks") {
                if store.sharedBlocks.isEmpty { Text("No shared blocks loaded").foregroundStyle(.secondary) }
                ForEach(store.sharedBlocks, id: \.number) { block in Text(block.number) }
                Text("Reports are reviewed before they can block a number for everyone. Caller ID can be spoofed.").font(.footnote).foregroundStyle(.secondary)
            }
            if let status = store.safetyStatus { Text(status).font(.footnote).foregroundStyle(.secondary) }
            Button("Sync Blocked Numbers") { Task { await store.refreshSafety() } }
                .disabled(!store.safetyBackend.isConfigured || store.syncingSafety)
        }
        .navigationTitle("Blocked Numbers")
        .task { await store.refreshSafety() }
    }
}
