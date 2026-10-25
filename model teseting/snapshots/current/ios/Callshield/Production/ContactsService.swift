import Contacts
import Foundation

enum ContactsAccess: Equatable { case notRequested, denied, available, limited }

protocol PhoneContactsService {
    var access: ContactsAccess { get }
    func requestAccess() async throws -> Bool
    func fetch() async throws -> [Person]
}

final class DeviceContactsService: PhoneContactsService {
    private let store = CNContactStore()
    var access: ContactsAccess {
        let status = CNContactStore.authorizationStatus(for: .contacts)
        if #available(iOS 18, *), status == .limited { return .limited }
        switch status {
        case .authorized: return .available
        case .notDetermined: return .notRequested
        default: return .denied
        }
    }
    func requestAccess() async throws -> Bool { try await store.requestAccess(for: .contacts) }
    func fetch() async throws -> [Person] {
        guard access == .available || access == .limited else { return [] }
        return try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    let store = CNContactStore()
                    var result: [Person] = []
                    var seen = Set<String>()
                    let request = CNContactFetchRequest(keysToFetch: [CNContactFormatter.descriptorForRequiredKeys(for: .fullName), CNContactPhoneNumbersKey as CNKeyDescriptor])
                    request.sortOrder = .userDefault
                    try store.enumerateContacts(with: request) { contact, _ in
                        let name = CNContactFormatter.string(from: contact, style: .fullName)
                        for phone in contact.phoneNumbers {
                            guard let number = try? PhoneNumber.normalized(phone.value.stringValue), seen.insert(number).inserted else { continue }
                            result.append(PhoneNumber.person(number, name: name))
                        }
                    }
                    continuation.resume(returning: result)
                } catch { continuation.resume(throwing: error) }
            }
        }
    }
}
