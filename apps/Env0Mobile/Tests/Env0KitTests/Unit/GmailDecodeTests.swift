import Foundation
import Testing
@testable import Env0Kit

@Suite("Gmail thread decoding")
struct GmailThreadDecodeTests {
    private let decoder = JSONCoding.makeDecoder()

    @Test("threads.list decodes stubs, optional envelope keys, string historyId")
    func threadList() throws {
        let json = """
        {
          "resultSizeEstimate": 42,
          "threads": [
            { "id": "f0e1d2c3b4a59687", "snippet": "Hey, can we sync on Q3 planning before...", "historyId": "1" },
            { "id": "9a8b7c6d5e4f3021", "snippet": "Your invoice for May is ready", "historyId": "1" }
          ],
          "nextPageToken": "100"
        }
        """
        let list = try decoder.decode(GmailThreadList.self, from: Data(json.utf8))
        #expect(list.resultSizeEstimate == 42)
        #expect(list.nextPageToken == "100")
        let threads = try #require(list.threads)
        #expect(threads.count == 2)
        #expect(threads[0].id == "f0e1d2c3b4a59687")
        #expect(threads[0].historyId == "1")
        #expect(threads[1].snippet == "Your invoice for May is ready")
    }

    @Test("threads.list omits threads and nextPageToken when empty")
    func threadListSparse() throws {
        let json = #"{ "resultSizeEstimate": 0 }"#
        let list = try decoder.decode(GmailThreadList.self, from: Data(json.utf8))
        #expect(list.resultSizeEstimate == 0)
        #expect(list.threads == nil)
        #expect(list.nextPageToken == nil)
    }

    @Test("threads.get decodes messages, payload tree and epoch-ms internalDate")
    func threadDetail() throws {
        let json = """
        {
          "id": "f0e1d2c3b4a59687",
          "historyId": "1",
          "messages": [
            {
              "id": "a1b2c3d4e5f6a7b8",
              "threadId": "f0e1d2c3b4a59687",
              "labelIds": ["INBOX", "UNREAD"],
              "snippet": "Hey, can we sync on Q3 planning before...",
              "historyId": "1",
              "internalDate": "1750257120000",
              "sizeEstimate": 412,
              "payload": {
                "partId": "",
                "mimeType": "text/plain",
                "filename": "",
                "headers": [
                  { "name": "From", "value": "Jordan Rivera <colleague@example.com>" },
                  { "name": "To", "value": "alex@nexusai.com" },
                  { "name": "Subject", "value": "Q3 planning" }
                ],
                "body": { "size": 256, "data": "SGV5LCBjYW4gd2Ugc3luYyBvbiBRMy4uLg" }
              }
            }
          ]
        }
        """
        let detail = try decoder.decode(GmailThreadDetail.self, from: Data(json.utf8))
        #expect(detail.id == "f0e1d2c3b4a59687")
        #expect(detail.historyId == "1")
        let messages = try #require(detail.messages)
        let msg = try #require(messages.first)
        #expect(msg.id == "a1b2c3d4e5f6a7b8")
        #expect(msg.labelIds == ["INBOX", "UNREAD"])
        #expect(msg.sizeEstimate == 412)
        #expect(msg.internalDate == "1750257120000")
        // internalDate parses via epochMillis.
        let date = try #require(msg.internalDateDate)
        #expect(abs(date.timeIntervalSince1970 - 1750257120) < 0.01)
        let payload = try #require(msg.payload)
        #expect(payload.mimeType == "text/plain")
        #expect(payload.parts == nil)
        let headers = try #require(payload.headers)
        #expect(headers.first?.name == "From")
        #expect(payload.body?.data == "SGV5LCBjYW4gd2Ugc3luYyBvbiBRMy4uLg")
        #expect(payload.body?.size == 256)
        #expect(payload.body?.attachmentId == nil)
    }

    @Test("multipart payload decodes nested parts recursively")
    func multipartPayload() throws {
        let json = """
        {
          "id": "t1",
          "messages": [
            {
              "id": "m1",
              "threadId": "t1",
              "payload": {
                "partId": "",
                "mimeType": "multipart/alternative",
                "filename": "",
                "headers": [],
                "body": { "size": 0 },
                "parts": [
                  { "partId": "0", "mimeType": "text/plain", "filename": "", "headers": [], "body": { "size": 10, "data": "cGxhaW4" } },
                  { "partId": "1", "mimeType": "text/html", "filename": "", "headers": [], "body": { "size": 20, "data": "PGI-aHRtbDwvYj4" } }
                ]
              }
            }
          ]
        }
        """
        let detail = try decoder.decode(GmailThreadDetail.self, from: Data(json.utf8))
        let payload = try #require(detail.messages?.first?.payload)
        #expect(payload.mimeType == "multipart/alternative")
        #expect(payload.body?.data == nil)
        let parts = try #require(payload.parts)
        #expect(parts.count == 2)
        #expect(parts[0].mimeType == "text/plain")
        #expect(parts[1].partId == "1")
        #expect(parts[1].body?.data == "PGI-aHRtbDwvYj4")
    }
}

@Suite("Gmail label decoding")
struct GmailLabelDecodeTests {
    private let decoder = JSONCoding.makeDecoder()

    @Test("labels.list decodes sparse system labels and a full user label")
    func labelList() throws {
        let json = """
        {
          "labels": [
            { "id": "INBOX", "name": "INBOX", "type": "system" },
            { "id": "IMPORTANT", "name": "IMPORTANT", "type": "system", "messageListVisibility": "hide", "labelListVisibility": "labelHide" },
            { "id": "Label_ab12cd34", "name": "Receipts", "type": "user", "messageListVisibility": "show", "labelListVisibility": "labelShow", "color": { "backgroundColor": "#16a765", "textColor": "#ffffff" } }
          ]
        }
        """
        let list = try decoder.decode(GmailLabelList.self, from: Data(json.utf8))
        let labels = try #require(list.labels)
        #expect(labels.count == 3)

        let inbox = labels[0]
        #expect(inbox.type == .system)
        #expect(inbox.messageListVisibility == nil)
        #expect(inbox.messagesTotal == nil)
        #expect(inbox.color == nil)

        let receipts = labels[2]
        #expect(receipts.type == .user)
        #expect(receipts.name == "Receipts")
        #expect(receipts.messageListVisibility == "show")
        #expect(receipts.color?.backgroundColor == "#16a765")
        #expect(receipts.color?.textColor == "#ffffff")
    }

    @Test("labels.get decodes populated counts")
    func labelGetWithCounts() throws {
        let json = """
        { "id": "INBOX", "name": "INBOX", "type": "system", "messagesTotal": 120, "messagesUnread": 7, "threadsTotal": 95, "threadsUnread": 5 }
        """
        let label = try decoder.decode(GmailLabel.self, from: Data(json.utf8))
        #expect(label.messagesTotal == 120)
        #expect(label.messagesUnread == 7)
        #expect(label.threadsTotal == 95)
        #expect(label.threadsUnread == 5)
    }

    @Test("unknown label type falls back to .unknown instead of throwing")
    func unknownLabelType() throws {
        let json = #"{ "id": "X", "name": "X", "type": "wizard" }"#
        let label = try decoder.decode(GmailLabel.self, from: Data(json.utf8))
        #expect(label.type == .unknown)
    }
}

@Suite("Gmail mutation responses")
struct GmailMutationDecodeTests {
    private let decoder = JSONCoding.makeDecoder()

    @Test("messages.modify returns the minimal message")
    func minimalMessage() throws {
        let json = #"{ "id": "a1b2c3d4e5f6a7b8", "threadId": "f0e1d2c3b4a59687", "labelIds": ["INBOX", "STARRED"] }"#
        let msg = try decoder.decode(GmailMinimalMessage.self, from: Data(json.utf8))
        #expect(msg.id == "a1b2c3d4e5f6a7b8")
        #expect(msg.threadId == "f0e1d2c3b4a59687")
        #expect(msg.labelIds == ["INBOX", "STARRED"])
    }

    @Test("messages.send returns SENT + INBOX labels")
    func sendResponse() throws {
        let json = #"{ "id": "c4d5e6f7a8b90123", "threadId": "f0e1d2c3b4a59687", "labelIds": ["SENT", "INBOX"] }"#
        let msg = try decoder.decode(GmailMinimalMessage.self, from: Data(json.utf8))
        #expect(msg.labelIds == ["SENT", "INBOX"])
    }

    @Test("drafts.create returns a draft with a minimal message")
    func draftCreate() throws {
        let json = """
        {
          "id": "d7e8f9a0b1c2d3e4",
          "message": { "id": "9f8e7d6c5b4a3210", "threadId": "1122334455667788", "labelIds": ["DRAFT"] }
        }
        """
        let draft = try decoder.decode(GmailDraft.self, from: Data(json.utf8))
        #expect(draft.id == "d7e8f9a0b1c2d3e4")
        let message = try #require(draft.message)
        #expect(message.id == "9f8e7d6c5b4a3210")
        #expect(message.threadId == "1122334455667788")
        #expect(message.labelIds == ["DRAFT"])
        // Full-only fields are absent on create and decode as nil.
        #expect(message.payload == nil)
        #expect(message.snippet == nil)
        #expect(message.internalDate == nil)
    }
}

@Suite("Gmail request encoding")
struct GmailRequestEncodeTests {
    @Test("modify body always carries both label arrays")
    func modifyBody() throws {
        let body = GmailModifyLabelsRequest(addLabelIds: ["STARRED"], removeLabelIds: ["UNREAD"])
        let data = try JSONCoding.makeEncoder().encode(body)
        let object = try #require(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        #expect(object["addLabelIds"] as? [String] == ["STARRED"])
        #expect(object["removeLabelIds"] as? [String] == ["UNREAD"])
    }

    @Test("draft create nests the message under message")
    func draftCreateBody() throws {
        let body = GmailDraftCreateRequest(message: GmailSendRequest(raw: "QUJD"))
        let data = try JSONCoding.makeEncoder().encode(body)
        let object = try #require(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        let message = try #require(object["message"] as? [String: Any])
        #expect(message["raw"] as? String == "QUJD")
    }
}
