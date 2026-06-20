import Foundation
import Testing
@testable import Env0Kit

@Suite("Docs document decoding")
struct DocsDocumentDecodeTests {
    private let decoder = JSONCoding.makeDecoder()

    @Test("documents.get decodes a two-paragraph doc, body tree and style maps")
    func getDocument() throws {
        // Fixture copied from gdoc.md "Operation 1 — Get a document".
        let json = """
        {
          "documentId": "4f9c2a1b8e7d4a6cb0f1e2d3c4b5a6f7",
          "title": "Q3 Planning Notes",
          "body": {
            "content": [
              {
                "endIndex": 1,
                "sectionBreak": {
                  "sectionStyle": {
                    "columnSeparatorStyle": "NONE",
                    "contentDirection": "LEFT_TO_RIGHT",
                    "sectionType": "CONTINUOUS"
                  }
                }
              },
              {
                "startIndex": 1,
                "endIndex": 19,
                "paragraph": {
                  "elements": [
                    {
                      "startIndex": 1,
                      "endIndex": 19,
                      "textRun": { "content": "Q3 Planning Notes\\n", "textStyle": {} }
                    }
                  ],
                  "paragraphStyle": { "namedStyleType": "NORMAL_TEXT", "direction": "LEFT_TO_RIGHT" }
                }
              },
              {
                "startIndex": 19,
                "endIndex": 53,
                "paragraph": {
                  "elements": [
                    {
                      "startIndex": 19,
                      "endIndex": 53,
                      "textRun": { "content": "Owner: Alex Thompson (CTO)\\n", "textStyle": {} }
                    }
                  ],
                  "paragraphStyle": { "namedStyleType": "NORMAL_TEXT", "direction": "LEFT_TO_RIGHT" }
                }
              }
            ]
          },
          "revisionId": "a1b2c3d4",
          "suggestionsViewMode": "DEFAULT_FOR_CURRENT_ACCESS",
          "documentStyle": {
            "pageNumberStart": 1,
            "marginTop": { "magnitude": 72, "unit": "PT" },
            "pageSize": { "height": { "magnitude": 792, "unit": "PT" }, "width": { "magnitude": 612, "unit": "PT" } },
            "useCustomHeaderFooterMargins": true
          },
          "namedStyles": {
            "styles": [
              { "namedStyleType": "NORMAL_TEXT" },
              { "namedStyleType": "HEADING_1", "textStyle": { "fontSize": { "magnitude": 20, "unit": "PT" } } }
            ]
          }
        }
        """
        let doc = try decoder.decode(GDocDocument.self, from: Data(json.utf8))
        #expect(doc.documentId == "4f9c2a1b8e7d4a6cb0f1e2d3c4b5a6f7")
        #expect(doc.title == "Q3 Planning Notes")
        #expect(doc.revisionId == "a1b2c3d4")
        #expect(doc.suggestionsViewMode == "DEFAULT_FOR_CURRENT_ACCESS")

        let content = try #require(doc.body?.content)
        #expect(content.count == 3)

        // First element is the section break (no paragraph).
        #expect(content[0].sectionBreak != nil)
        #expect(content[0].paragraph == nil)
        #expect(content[0].endIndex == 1)

        // Second element is a paragraph with one text run.
        let para = try #require(content[1].paragraph)
        let run = try #require(para.elements?.first?.textRun)
        #expect(run.content == "Q3 Planning Notes\n")
        #expect(para.paragraphStyle?.namedStyleType == "NORMAL_TEXT")

        // Style maps round-trip as free-form JSONValue.
        #expect(doc.documentStyle?["pageNumberStart"]?.doubleValue == 1)
        let margin = try #require(doc.documentStyle?["marginTop"]?.objectValue)
        #expect(margin["unit"]?.stringValue == "PT")
        #expect(margin["magnitude"]?.doubleValue == 72)
        #expect(doc.namedStyles?["styles"]?.arrayValue?.count == 2)
    }

    @Test("plainText concatenates every textRun content in order")
    func plainTextExtraction() throws {
        let json = """
        {
          "documentId": "doc1",
          "title": "Notes",
          "body": { "content": [
            { "endIndex": 1, "sectionBreak": { "sectionStyle": {} } },
            { "paragraph": { "elements": [ { "textRun": { "content": "Q3 Planning Notes\\n" } } ] } },
            { "paragraph": { "elements": [ { "textRun": { "content": "Owner: Alex Thompson (CTO)\\n" } } ] } }
          ] },
          "revisionId": "a1b2c3d4"
        }
        """
        let doc = try decoder.decode(GDocDocument.self, from: Data(json.utf8))
        #expect(doc.plainText == "Q3 Planning Notes\nOwner: Alex Thompson (CTO)\n")
    }

    @Test("plainText descends into table cells")
    func plainTextTable() throws {
        let json = """
        {
          "documentId": "doc2",
          "title": "Has a table",
          "body": { "content": [
            { "paragraph": { "elements": [ { "textRun": { "content": "Before\\n" } } ] } },
            { "table": { "rows": 1, "columns": 2, "tableRows": [
              { "tableCells": [
                { "content": [ { "paragraph": { "elements": [ { "textRun": { "content": "A\\n" } } ] } } ] },
                { "content": [ { "paragraph": { "elements": [ { "textRun": { "content": "B\\n" } } ] } } ] }
              ] }
            ] } },
            { "paragraph": { "elements": [ { "textRun": { "content": "After\\n" } } ] } }
          ] },
          "revisionId": "r1"
        }
        """
        let doc = try decoder.decode(GDocDocument.self, from: Data(json.utf8))
        #expect(doc.plainText == "Before\nA\nB\nAfter\n")
    }

    @Test("create response decodes the empty-body document; sparse maps are nil")
    func createResponse() throws {
        // Fixture copied from gdoc.md "Operation 2 — Create a document".
        let json = """
        {
          "documentId": "0a1b2c3d4e5f60718293a4b5c6d7e8f9",
          "title": "My new doc",
          "body": { "content": [
            { "endIndex": 1, "sectionBreak": { "sectionStyle": { "sectionType": "CONTINUOUS" } } },
            { "startIndex": 1, "endIndex": 2, "paragraph": {
              "elements": [ { "startIndex": 1, "endIndex": 2, "textRun": { "content": "\\n", "textStyle": {} } } ],
              "paragraphStyle": { "namedStyleType": "NORMAL_TEXT", "direction": "LEFT_TO_RIGHT" }
            } }
          ] },
          "revisionId": "9f8e7d6c",
          "suggestionsViewMode": "DEFAULT_FOR_CURRENT_ACCESS",
          "documentStyle": { "pageNumberStart": 1 },
          "namedStyles": { "styles": [] }
        }
        """
        let doc = try decoder.decode(GDocDocument.self, from: Data(json.utf8))
        #expect(doc.documentId == "0a1b2c3d4e5f60718293a4b5c6d7e8f9")
        #expect(doc.title == "My new doc")
        #expect(doc.revisionId == "9f8e7d6c")
        // Empty new doc: just the trailing newline.
        #expect(doc.plainText == "\n")
        // Maps that the server omits decode as nil.
        #expect(doc.lists == nil)
        #expect(doc.inlineObjects == nil)
        #expect(doc.headers == nil)
        #expect(doc.footers == nil)
        #expect(doc.namedRanges == nil)
    }
}

@Suite("Docs save + batchUpdate responses")
struct DocsMutationDecodeTests {
    private let decoder = JSONCoding.makeDecoder()

    @Test("save response decodes snake_case modified_time and parses the date")
    func saveResponse() throws {
        // Fixture copied from gdoc.md "Operation 3.B — web-editor save".
        let json = #"{ "status": "ok", "modified_time": "2026-06-20T14:32:01.123456+00:00" }"#
        let response = try decoder.decode(SaveResponse.self, from: Data(json.utf8))
        #expect(response.status == "ok")
        #expect(response.modifiedTime == "2026-06-20T14:32:01.123456+00:00")
        let date = try #require(response.modifiedTimeDate)
        // 2026-06-20T14:32:01Z plus ~0.123s of fractional seconds.
        let expected = try #require(DateParsing.rfc3339("2026-06-20T14:32:01Z"))
        #expect(abs(date.timeIntervalSince1970 - expected.timeIntervalSince1970 - 0.123456) < 0.01)
    }

    @Test("batchUpdate response decodes parallel replies and the new revision id")
    func batchUpdateResponse() throws {
        // Fixture copied from gdoc.md "Operation 3.A — batchUpdate".
        let json = """
        {
          "documentId": "4f9c2a1b8e7d4a6cb0f1e2d3c4b5a6f7",
          "replies": [
            {},
            { "replaceAllText": { "occurrencesChanged": 3 } }
          ],
          "writeControl": { "requiredRevisionId": "b2c3d4e5" }
        }
        """
        let response = try decoder.decode(BatchUpdateResponse.self, from: Data(json.utf8))
        #expect(response.documentId == "4f9c2a1b8e7d4a6cb0f1e2d3c4b5a6f7")
        let replies = try #require(response.replies)
        #expect(replies.count == 2)
        #expect(replies[0] == .object([:]))
        let reply = try #require(replies[1].objectValue?["replaceAllText"]?.objectValue)
        #expect(reply["occurrencesChanged"]?.doubleValue == 3)
        #expect(response.writeControl?.requiredRevisionId == "b2c3d4e5")
    }
}

@Suite("Docs request encoding")
struct DocsRequestEncodeTests {
    @Test("create body carries only the title")
    func createBody() throws {
        let data = try JSONCoding.makeEncoder().encode(CreateDocRequest(title: "My new doc"))
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(object["title"] as? String == "My new doc")
        #expect(object.count == 1)
    }

    @Test("save body carries content and format")
    func saveBody() throws {
        let data = try JSONCoding.makeEncoder().encode(
            SaveRequest(content: "Line one\nLine two\n\nNew paragraph", format: "text")
        )
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(object["content"] as? String == "Line one\nLine two\n\nNew paragraph")
        #expect(object["format"] as? String == "text")
    }

    @Test("batchUpdate insertText builder encodes the canonical shape")
    func insertTextBuilder() throws {
        let request = BatchUpdateRequest(
            requests: [DocsBatchUpdate.insertText(at: 1, text: "Hello world\n")]
        )
        let data = try JSONCoding.makeEncoder().encode(request)
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let requests = try #require(object["requests"] as? [[String: Any]])
        let insert = try #require(requests.first?["insertText"] as? [String: Any])
        #expect(insert["text"] as? String == "Hello world\n")
        let location = try #require(insert["location"] as? [String: Any])
        #expect(location["index"] as? Double == 1)
    }

    @Test("batchUpdate replaceAllText builder encodes containsText + replaceText")
    func replaceAllTextBuilder() throws {
        let request = BatchUpdateRequest(
            requests: [DocsBatchUpdate.replaceAllText(containing: "foo", matchCase: true, with: "bar")],
            writeControl: WriteControl(requiredRevisionId: "a1b2c3d4")
        )
        let data = try JSONCoding.makeEncoder().encode(request)
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect((object["writeControl"] as? [String: Any])?["requiredRevisionId"] as? String == "a1b2c3d4")
        let requests = try #require(object["requests"] as? [[String: Any]])
        let replace = try #require(requests.first?["replaceAllText"] as? [String: Any])
        #expect(replace["replaceText"] as? String == "bar")
        let contains = try #require(replace["containsText"] as? [String: Any])
        #expect(contains["text"] as? String == "foo")
        #expect(contains["matchCase"] as? Bool == true)
    }
}
