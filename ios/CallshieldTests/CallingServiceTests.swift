import Foundation
import XCTest
@testable import Callshield

private final class CallingResponseProtocol: URLProtocol {
    static var responseBody = Data()
    static var status = 200
    static var requests: [URLRequest] = []
    override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "callshield.test" }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        let response = HTTPURLResponse(url: request.url!, statusCode: Self.status, httpVersion: "HTTP/1.1",
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.responseBody)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

final class CallingServiceTests: XCTestCase {
    private var client: CallingServiceClient!
    override func setUp() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CallingResponseProtocol.self]
        client = CallingServiceClient(baseURL: URL(string: "https://callshield.test")!, credential: "user-test-session",
                                      session: URLSession(configuration: configuration))
        CallingResponseProtocol.requests = []; CallingResponseProtocol.status = 200
    }
    override func tearDown() { client.session.invalidateAndCancel() }
    func testTokenAndCallerSubscriptionUseAuthenticatedServerContracts() async throws {
        CallingResponseProtocol.responseBody = Data(#"{"token":"short-lived-sdk-token","identity":"authenticated-user"}"#.utf8)
        let token: CallingServiceClient.Token = try await client.post("voice/token", body: [:])
        XCTAssertEqual(token.identity, "authenticated-user")
        XCTAssertEqual(CallingResponseProtocol.requests.last?.url?.path, "/voice/token")
        XCTAssertEqual(CallingResponseProtocol.requests.last?.value(forHTTPHeaderField: "Authorization"), "Bearer user-test-session")
        CallingResponseProtocol.responseBody = Data(#"{"audio_url":"wss://relay.test/audio/uuid","bearer_token":"per-call-token","caller_track":"outbound","call_sid":"CA_caller_leg"}"#.utf8)
        let sub: CallingServiceClient.Subscription = try await client.post("voice/analysis", body: ["call_sid": "CA_sdk", "call_uuid": UUID().uuidString, "direction": "incoming"])
        XCTAssertEqual(sub.configuration.callSID, "CA_caller_leg")
        XCTAssertEqual(sub.configuration.callerTrack, "outbound")
        XCTAssertEqual(CallingResponseProtocol.requests.last?.url?.path, "/voice/analysis")
    }
    func testRejectedAndMalformedServerResponsesFailExplicitly() async throws {
        CallingResponseProtocol.status = 401
        do {
            let _: CallingServiceClient.Token = try await client.post("voice/token", body: [:])
            XCTFail("Rejected session must not configure SDK")
        } catch { XCTAssertTrue(error is CallingServiceError) }
        CallingResponseProtocol.status = 200; CallingResponseProtocol.responseBody = Data("{}".utf8)
        do {
            let _: CallingServiceClient.Token = try await client.post("voice/token", body: [:])
            XCTFail("Malformed response must not configure SDK")
        } catch { XCTAssertTrue(error is CallingServiceError) }
    }
}
