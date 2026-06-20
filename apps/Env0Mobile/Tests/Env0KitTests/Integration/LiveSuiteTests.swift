import Foundation
import Testing
@testable import Env0Kit

// These tests hit *live* env-0 mock servers and are therefore opt-in: they only
// run when ENV0_INTEGRATION=1. Start the servers first with
// `scripts/run_local_services.sh start`, then:
//   ENV0_INTEGRATION=1 swift test --filter Live
// Base URLs default to the config.toml localhost ports but can be overridden via
// ENV0_GMAIL_URL / ENV0_CALENDAR_URL / ENV0_DOCS_URL / ENV0_DRIVE_URL.
private let integrationEnabled = ProcessInfo.processInfo.environment["ENV0_INTEGRATION"] == "1"

private func liveSuite() -> Env0Suite {
    let env = ProcessInfo.processInfo.environment
    func url(_ key: String, _ fallback: String) -> URL { URL(string: env[key] ?? fallback)! }
    let environment = Env0Environment(
        gmail: url("ENV0_GMAIL_URL", "http://127.0.0.1:9001"),
        calendar: url("ENV0_CALENDAR_URL", "http://127.0.0.1:9003"),
        docs: url("ENV0_DOCS_URL", "http://127.0.0.1:9004"),
        drive: url("ENV0_DRIVE_URL", "http://127.0.0.1:9005")
    )
    return Env0Suite(environment: environment)
}

@Suite("Live env-0 integration", .serialized, .enabled(if: integrationEnabled))
struct LiveIntegrationTests {
    let suite = liveSuite()

    @Test("all four services report healthy")
    func healthAllUp() async {
        let health = await suite.health()
        #expect(health.gmail)
        #expect(health.calendar)
        #expect(health.docs)
        #expect(health.drive)
    }

    @Test("gmail: list threads, read one, find INBOX label")
    func gmailReadFlow() async throws {
        let list = try await suite.gmail.listThreads(maxResults: 5)
        #expect(list.resultSizeEstimate >= 1)
        let threads = try #require(list.threads, "seeded mailbox should have threads")
        #expect(!threads.isEmpty)

        let detail = try await suite.gmail.getThread(id: threads[0].id)
        let messages = try #require(detail.messages)
        #expect(!messages.isEmpty)
        #expect(messages[0].payload != nil)

        let labels = try await suite.gmail.listLabels()
        #expect(labels.contains { $0.id == "INBOX" })
    }

    @Test("gmail: star then unstar round-trips a message")
    func gmailStarRoundTrip() async throws {
        let list = try await suite.gmail.listThreads(maxResults: 1)
        let thread = try #require(list.threads?.first)
        let detail = try await suite.gmail.getThread(id: thread.id)
        let messageId = try #require(detail.messages?.first?.id)

        let starred = try await suite.gmail.star(messageId: messageId)
        #expect(starred.labelIds?.contains("STARRED") == true)
        let unstarred = try await suite.gmail.unstar(messageId: messageId)
        #expect(unstarred.labelIds?.contains("STARRED") != true)
    }

    @Test("calendar: list calendars, list + get events on primary")
    func calendarReadFlow() async throws {
        let calendars = try await suite.calendar.listCalendars()
        let items = try #require(calendars.items, "should expose at least the primary calendar")
        #expect(!items.isEmpty)
        let primary = items.first { $0.primary == true } ?? items[0]

        let events = try await suite.calendar.listEvents(calendarId: primary.id)
        if let first = events.items?.first {
            let fetched = try await suite.calendar.getEvent(calendarId: primary.id, eventId: first.id)
            #expect(fetched.id == first.id)
        }
    }

    @Test("docs: create a document then read it back")
    func docsCreateRead() async throws {
        let title = "Env0Mobile smoke \(UUID().uuidString.prefix(8))"
        let created = try await suite.docs.createDocument(title: title)
        #expect(!created.documentId.isEmpty)

        let fetched = try await suite.docs.getDocument(documentId: created.documentId)
        #expect(fetched.title == title)
        _ = fetched.plainText // exercises the body text extractor
    }

    @Test("drive: list files and read one's metadata")
    func driveReadFlow() async throws {
        let list = try await suite.drive.listFiles(pageSize: 10)
        let files = list.files ?? []
        if let first = files.first, let id = first.id {
            let meta = try await suite.drive.getFile(fileId: id)
            #expect(meta.id == id)
        }
    }
}
