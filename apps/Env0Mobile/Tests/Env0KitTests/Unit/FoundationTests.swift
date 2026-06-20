import Foundation
import Testing
@testable import Env0Kit

@Suite("Networking foundation")
struct FoundationTests {
    @Test("Endpoint builds a URL with path and query")
    func endpointURL() throws {
        let base = URL(string: "http://127.0.0.1:9001")!
        let endpoint = Endpoint(
            "/users/me/threads",
            query: [URLQueryItem(name: "q", value: "is:unread"), URLQueryItem(name: "maxResults", value: "10")]
        )
        let url = try #require(endpoint.url(relativeTo: base))
        #expect(url.absoluteString == "http://127.0.0.1:9001/users/me/threads?q=is:unread&maxResults=10"
            || url.absoluteString == "http://127.0.0.1:9001/users/me/threads?q=is%3Aunread&maxResults=10")
    }

    @Test("Endpoint without query emits no trailing question mark")
    func endpointNoQuery() throws {
        let base = URL(string: "http://h:9004")!
        let url = try #require(Endpoint("documents/abc").url(relativeTo: base))
        #expect(url.absoluteString == "http://h:9004/documents/abc")
    }

    @Test("optional query item drops nil values")
    func optionalQuery() {
        #expect(URLQueryItem.optional("q", nil) == nil)
        #expect(URLQueryItem.optional("q", "x") == URLQueryItem(name: "q", value: "x"))
    }

    @Test("RFC3339 parses with and without fractional seconds")
    func rfc3339() throws {
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC")!
        let expected = try #require(utc.date(from: DateComponents(
            year: 2026, month: 6, day: 20, hour: 10, minute: 0, second: 0)))
        let withFraction = try #require(DateParsing.rfc3339("2026-06-20T10:00:00.123Z"))
        let plain = try #require(DateParsing.rfc3339("2026-06-20T10:00:00Z"))
        #expect(abs(plain.timeIntervalSince1970 - expected.timeIntervalSince1970) < 0.01)
        #expect(abs(withFraction.timeIntervalSince1970 - plain.timeIntervalSince1970 - 0.123) < 0.01)
        #expect(DateParsing.rfc3339(nil) == nil)
        #expect(DateParsing.rfc3339("") == nil)
    }

    @Test("epoch millis string parses to a Date")
    func epochMillis() throws {
        let date = try #require(DateParsing.epochMillis("1781258400000"))
        #expect(abs(date.timeIntervalSince1970 - 1781258400) < 0.01)
        #expect(DateParsing.epochMillis("not-a-number") == nil)
    }

    @Test("all-day calendar date parses at UTC midnight")
    func calendarDay() throws {
        let date = try #require(DateParsing.calendarDay("2026-06-20"))
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC")!
        let comps = utc.dateComponents([.year, .month, .day, .hour], from: date)
        #expect(comps.year == 2026 && comps.month == 6 && comps.day == 20 && comps.hour == 0)
    }

    @Test("Google error envelope decodes a message")
    func errorEnvelope() throws {
        let json = Data(#"{"error":{"code":404,"message":"Not Found","status":"NOT_FOUND"}}"#.utf8)
        let envelope = try JSONCoding.makeDecoder().decode(GoogleErrorEnvelope.self, from: json)
        #expect(envelope.error.message == "Not Found")
        #expect(envelope.error.code == 404)
    }

    @Test("Env0Error has a human-readable description")
    func errorDescription() {
        #expect(Env0Error.http(status: 500, message: "boom").errorDescription == "HTTP 500: boom")
        #expect(Env0Error.http(status: 404, message: nil).errorDescription == "HTTP 404")
        #expect(Env0Error.transport("cancelled").isCancellation)
    }
}

/// A stub transport that returns canned bytes, to exercise the decode/run path
/// of `Env0Requesting` without a network.
struct StubTransport: Env0Requesting {
    let payload: Data
    func data(for endpoint: Endpoint) async throws -> Data { payload }
}

@Suite("Env0Requesting decode path")
struct DecodePathTests {
    struct Sample: Codable, Sendable, Equatable { let id: String; let count: Int }

    @Test("get decodes the canned body")
    func decodes() async throws {
        let stub = StubTransport(payload: Data(#"{"id":"x","count":3}"#.utf8))
        let value = try await stub.get(Sample.self, Endpoint("anything"))
        #expect(value == Sample(id: "x", count: 3))
    }

    @Test("get surfaces a decoding error as Env0Error.decoding")
    func decodeFailure() async {
        let stub = StubTransport(payload: Data(#"{"id":"x"}"#.utf8)) // missing count
        await #expect(throws: Env0Error.self) {
            _ = try await stub.get(Sample.self, Endpoint("anything"))
        }
    }
}

@Suite("Environment presets")
struct EnvironmentTests {
    @Test("localPorts maps the config.toml ports")
    func localPorts() {
        let env = Env0Environment.localPorts(host: "10.0.0.5")
        #expect(env.gmail.absoluteString == "http://10.0.0.5:9001")
        #expect(env.calendar.absoluteString == "http://10.0.0.5:9003")
        #expect(env.docs.absoluteString == "http://10.0.0.5:9004")
        #expect(env.drive.absoluteString == "http://10.0.0.5:9005")
        #expect(env.auth?.absoluteString == "http://10.0.0.5:9000")
    }

    @Test("gateway maps subdomains")
    func gateway() {
        let env = Env0Environment.gateway()
        #expect(env.gmail.absoluteString == "http://gmail.localhost:8080")
        #expect(env.calendar.absoluteString == "http://gcal.localhost:8080")
    }
}
