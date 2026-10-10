import Foundation
import LiveCommunicationKit
import UIKit

@MainActor
protocol SystemPhoneService {
    func dial(_ number: String) async throws
    func recentCalls() async throws -> [PhoneCallRecord]
}

@MainActor
final class AppleSystemPhoneService: SystemPhoneService {
    private let usesDefaultDialer: Bool
    init(usesDefaultDialer: Bool = AppConfiguration.defaultDialerEnabled) { self.usesDefaultDialer = usesDefaultDialer }

    func dial(_ number: String) async throws {
        let number = try PhoneNumber.normalized(number)
        #if targetEnvironment(simulator)
        throw PhoneError.simulatorUnavailable
        #else
        if #available(iOS 26, *), usesDefaultDialer {
            let handle = Handle(type: .phoneNumber, value: number)
            try await TelephonyConversationManager.sharedInstance.startCellularConversation(
                StartCellularConversationAction(handle, cellularService: nil))
            return
        }
        var components = URLComponents()
        if #available(iOS 18.2, *) { components.scheme = "telephony" }
        else { components.scheme = "tel" }
        components.path = number
        guard let url = components.url else { throw PhoneError.invalidNumber }
        let opened = await UIApplication.shared.open(url)
        guard opened else { throw PhoneError.actionUnavailable }
        #endif
    }

    func recentCalls() async throws -> [PhoneCallRecord] {
        guard usesDefaultDialer else { return [] }
        if #available(iOS 26, *) {
            let results = try await ConversationHistoryManager.sharedInstance.recentConversations(
                matching: #Predicate<ConversationHistoryManager.RecentConversation> { _ in true })
            return results.compactMap { call in
                guard let number = call.handles.first(where: { $0.type == .phoneNumber })?.value else { return nil }
                let outcome: PhoneCallOutcome
                switch call.status {
                case .connected: outcome = .completed
                case .missed: outcome = .missed
                case .answeredElsewhere: outcome = .answeredElsewhere
                case .cancelled: outcome = .cancelled
                case .unknown: outcome = .failed
                @unknown default: outcome = .failed
                }
                return PhoneCallRecord(id: call.id, person: PhoneNumber.person(number), date: call.date,
                                       duration: max(0, Int(call.duration)), direction: call.direction == .incoming ? .incoming : .outgoing,
                                       outcome: outcome, voice: .unknown)
            }
        }
        return []
    }
}
