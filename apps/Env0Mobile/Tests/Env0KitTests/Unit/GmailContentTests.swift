import Foundation
import Testing
@testable import Env0Kit

@Suite("Gmail message content helpers")
struct GmailContentTests {
    // "Hello world" base64url, no padding.
    static let helloBody = "SGVsbG8gd29ybGQ"

    func sampleMessage() throws -> GmailMessage {
        let json = Data("""
        {
          "id": "m1",
          "threadId": "t1",
          "labelIds": ["INBOX", "UNREAD"],
          "internalDate": "1750257120000",
          "payload": {
            "mimeType": "text/plain",
            "headers": [
              {"name": "From", "value": "Jordan Rivera <jordan@example.com>"},
              {"name": "To", "value": "alex@nexusai.com"},
              {"name": "Subject", "value": "Q3 planning"}
            ],
            "body": {"size": 11, "data": "\(Self.helloBody)"}
          }
        }
        """.utf8)
        return try JSONCoding.makeDecoder().decode(GmailMessage.self, from: json)
    }

    @Test("extracts headers case-insensitively")
    func headers() throws {
        let message = try sampleMessage()
        #expect(message.subject == "Q3 planning")
        #expect(message.from == "Jordan Rivera <jordan@example.com>")
        #expect(message.headerValue("SUBJECT") == "Q3 planning")
        #expect(message.headerValue("Reply-To") == nil)
    }

    @Test("decodes base64url body to text")
    func bodyText() throws {
        let message = try sampleMessage()
        #expect(message.bodyText == "Hello world")
    }

    @Test("bestDate uses internalDate epoch millis")
    func bestDate() throws {
        let message = try sampleMessage()
        let date = try #require(message.bestDate)
        #expect(abs(date.timeIntervalSince1970 - 1750257120) < 0.01)
    }

    @Test("finds text/plain inside a multipart payload")
    func multipart() throws {
        let json = Data("""
        {
          "id": "m2", "threadId": "t2",
          "payload": {
            "mimeType": "multipart/alternative",
            "parts": [
              {"mimeType": "text/html", "body": {"data": ""}},
              {"mimeType": "text/plain", "body": {"data": "\(Self.helloBody)"}}
            ]
          }
        }
        """.utf8)
        let message = try JSONCoding.makeDecoder().decode(GmailMessage.self, from: json)
        #expect(message.bodyText == "Hello world")
    }

    @Test("GmailCompose raw round-trips through base64url")
    func composeRoundTrip() throws {
        let compose = GmailCompose(to: "a@b.com", subject: "Hi", body: "Line one\nLine two")
        let raw = compose.rawValue()
        let decoded = try #require(Data(base64URLEncoded: raw))
        let text = String(decoding: decoded, as: UTF8.self)
        #expect(text.contains("To: a@b.com"))
        #expect(text.contains("Subject: Hi"))
        #expect(text.contains("Line one\nLine two"))
        #expect(!raw.contains("="))  // unpadded base64url
    }
}
