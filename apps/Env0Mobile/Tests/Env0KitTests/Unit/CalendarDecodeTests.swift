import Foundation
import Testing
@testable import Env0Kit

@Suite("Calendar calendarList decoding")
struct CalendarListDecodeTests {
    let json = """
    {
      "kind": "calendar#calendarList",
      "etag": "\\"a1b2c3\\"",
      "items": [
        {
          "kind": "calendar#calendarListEntry",
          "etag": "\\"d4e5f6\\"",
          "id": "primary-alex@nexusai.com",
          "summary": "alex@nexusai.com",
          "timeZone": "UTC",
          "accessRole": "owner",
          "primary": true,
          "selected": true,
          "colorId": "14",
          "backgroundColor": "#039be5",
          "foregroundColor": "#ffffff",
          "conferenceProperties": { "allowedConferenceSolutionTypes": ["hangoutsMeet"] },
          "defaultReminders": [ { "method": "popup", "minutes": 10 } ],
          "notificationSettings": {
            "notifications": [
              { "type": "eventCreation", "method": "email" },
              { "type": "eventResponse", "method": "email" }
            ]
          }
        },
        {
          "kind": "calendar#calendarListEntry",
          "etag": "\\"99aa\\"",
          "id": "team-alex@nexusai.com",
          "summary": "NexusAI Engineering",
          "description": "Team rituals, sprint planning, and engineering meetings",
          "timeZone": "UTC",
          "accessRole": "owner",
          "selected": true,
          "colorId": "9",
          "dataOwner": "alex@nexusai.com"
        }
      ],
      "nextSyncToken": "7c4a8d09ca37"
    }
    """

    @Test("decodes envelope and entries")
    func decodesList() throws {
        let list = try JSONCoding.makeDecoder().decode(CalendarList.self, from: Data(json.utf8))
        #expect(list.kind == "calendar#calendarList")
        let items = try #require(list.items)
        #expect(items.count == 2)
        #expect(list.nextSyncToken == "7c4a8d09ca37")
        // Absent on the wire -> nil.
        #expect(list.nextPageToken == nil)
    }

    @Test("primary calendar keeps reminders + notifications, non-primary keeps dataOwner")
    func sparseFields() throws {
        let list = try JSONCoding.makeDecoder().decode(CalendarList.self, from: Data(json.utf8))
        let primary = try #require(list.items?.first)
        #expect(primary.primary == true)
        #expect(primary.accessRole == .owner)
        #expect(primary.defaultReminders?.first?.minutes == 10)
        #expect(primary.notificationSettings?.notifications?.count == 2)
        #expect(primary.conferenceProperties?.allowedConferenceSolutionTypes == ["hangoutsMeet"])
        // Non-primary: primary omitted -> nil; dataOwner + description present.
        let team = try #require(list.items?.last)
        #expect(team.primary == nil)
        #expect(team.dataOwner == "alex@nexusai.com")
        #expect(team.description == "Team rituals, sprint planning, and engineering meetings")
        #expect(team.defaultReminders == nil)
    }

    @Test("unknown accessRole falls back instead of throwing")
    func accessRoleFallback() throws {
        let weird = """
        { "kind": "calendar#calendarListEntry", "etag": "x", "id": "c1",
          "summary": "S", "timeZone": "UTC", "accessRole": "superAdmin" }
        """
        let entry = try JSONCoding.makeDecoder().decode(CalendarListEntry.self, from: Data(weird.utf8))
        #expect(entry.accessRole == .unknown)
    }
}

@Suite("Calendar event decoding")
struct CalendarEventDecodeTests {
    let timedJSON = """
    {
      "kind": "calendar#event",
      "etag": "\\"3858f62230ac3c91\\"",
      "id": "evt_abc123def456",
      "status": "confirmed",
      "htmlLink": "https://www.google.com/calendar/event?eid=evt_abc123def456",
      "created": "2026-06-15T09:00:00Z",
      "updated": "2026-06-18T14:30:00Z",
      "summary": "Q2 Planning Kickoff",
      "description": "Finalize engineering priorities for Q2.",
      "location": "Zoom",
      "iCalUID": "f1e2d3c4b5a6@google.com",
      "sequence": 0,
      "start": { "dateTime": "2026-06-22T10:00:00Z", "timeZone": "UTC" },
      "end":   { "dateTime": "2026-06-22T12:00:00Z", "timeZone": "UTC" },
      "attendees": [
        { "email": "sarah.kim@nexusai.com",    "responseStatus": "accepted" },
        { "email": "marcus.rivera@nexusai.com","responseStatus": "needsAction" }
      ],
      "creator":   { "email": "alex@nexusai.com", "self": true },
      "organizer": { "email": "alex@nexusai.com", "self": true, "displayName": "NexusAI Engineering" },
      "reminders": { "useDefault": true },
      "eventType": "default"
    }
    """

    @Test("decodes a timed event with attendees and actors")
    func decodesTimedEvent() throws {
        let event = try JSONCoding.makeDecoder().decode(CalendarEvent.self, from: Data(timedJSON.utf8))
        #expect(event.id == "evt_abc123def456")
        #expect(event.status == .confirmed)
        #expect(event.summary == "Q2 Planning Kickoff")
        #expect(event.iCalUID == "f1e2d3c4b5a6@google.com")
        #expect(event.sequence == 0)
        #expect(event.attendees?.count == 2)
        #expect(event.attendees?.first?.responseStatus == .accepted)
        let organizer = try #require(event.organizer)
        #expect(organizer.isSelf == true)
        #expect(organizer.displayName == "NexusAI Engineering")
        #expect(event.reminders?.useDefault == true)
        // recurrence absent -> nil (sparse).
        #expect(event.recurrence == nil)
    }

    @Test("dateTime parses to RFC3339 Date; all-day date parses separately")
    func dateParsing() throws {
        let event = try JSONCoding.makeDecoder().decode(CalendarEvent.self, from: Data(timedJSON.utf8))
        let start = try #require(event.start?.dateTimeDate)
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC")!
        let comps = utc.dateComponents([.year, .month, .day, .hour], from: start)
        #expect(comps.year == 2026 && comps.month == 6 && comps.day == 22 && comps.hour == 10)
        // Timed event: no all-day date.
        #expect(event.start?.dateDate == nil)
        // created/updated computed dates.
        #expect(event.createdDate != nil)
        #expect(event.updatedDate != nil)
    }

    @Test("all-day event uses date, not dateTime")
    func allDayEvent() throws {
        let allDay = """
        { "kind": "calendar#event", "etag": "e", "id": "evt_allday",
          "status": "confirmed", "iCalUID": "x@google.com", "sequence": 0,
          "start": { "date": "2026-06-25" }, "end": { "date": "2026-06-26" } }
        """
        let event = try JSONCoding.makeDecoder().decode(CalendarEvent.self, from: Data(allDay.utf8))
        #expect(event.start?.dateTime == nil)
        #expect(event.start?.dateTimeDate == nil)
        let day = try #require(event.start?.dateDate)
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC")!
        let comps = utc.dateComponents([.year, .month, .day], from: day)
        #expect(comps.year == 2026 && comps.month == 6 && comps.day == 25)
        #expect(event.start?.resolvedDate == day)
        // No attendees -> nil.
        #expect(event.attendees == nil)
    }

    @Test("unknown status and responseStatus fall back")
    func enumFallback() throws {
        let weird = """
        { "kind": "calendar#event", "etag": "e", "id": "evt_x",
          "status": "archived", "iCalUID": "x@google.com", "sequence": 1,
          "start": { "dateTime": "2026-06-22T10:00:00Z" },
          "end": { "dateTime": "2026-06-22T11:00:00Z" },
          "attendees": [ { "email": "a@b.com", "responseStatus": "maybe-later" } ] }
        """
        let event = try JSONCoding.makeDecoder().decode(CalendarEvent.self, from: Data(weird.utf8))
        #expect(event.status == .unknown)
        #expect(event.attendees?.first?.responseStatus == .unknown)
    }

    @Test("events.list envelope keeps items and sparse fields")
    func eventListEnvelope() throws {
        let listJSON = """
        {
          "kind": "calendar#events",
          "etag": "\\"listetag\\"",
          "summary": "NexusAI Engineering",
          "timeZone": "UTC",
          "updated": "2026-06-22T12:00:00Z",
          "accessRole": "owner",
          "defaultReminders": [ { "method": "popup", "minutes": 10 } ],
          "items": [
            { "kind": "calendar#event", "etag": "e", "id": "evt_1", "status": "confirmed",
              "iCalUID": "i@google.com", "sequence": 0,
              "start": { "dateTime": "2026-06-22T10:00:00Z" },
              "end": { "dateTime": "2026-06-22T11:00:00Z" } }
          ]
        }
        """
        let list = try JSONCoding.makeDecoder().decode(EventList.self, from: Data(listJSON.utf8))
        #expect(list.kind == "calendar#events")
        #expect(list.summary == "NexusAI Engineering")
        #expect(list.accessRole == .owner)
        #expect(list.items?.count == 1)
        #expect(list.items?.first?.id == "evt_1")
        #expect(list.updatedDate != nil)
        #expect(list.nextPageToken == nil)
    }
}

@Suite("Calendar request encoding")
struct CalendarRequestEncodeTests {
    @Test("EventWriteRequest omits nil keys and keeps start/end")
    func encodeWrite() throws {
        let req = EventWriteRequest(
            summary: "Design review",
            start: EventDateTime(dateTime: "2026-06-25T15:00:00Z", timeZone: "UTC"),
            end: EventDateTime(dateTime: "2026-06-25T16:00:00Z", timeZone: "UTC"),
            attendees: [EventAttendee(email: "priya.sharma@nexusai.com")]
        )
        let data = try JSONCoding.makeEncoder().encode(req)
        let obj = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(obj["summary"] as? String == "Design review")
        #expect(obj["description"] == nil) // nil -> omitted
        let start = try #require(obj["start"] as? [String: Any])
        #expect(start["dateTime"] as? String == "2026-06-25T15:00:00Z")
        let attendees = try #require(obj["attendees"] as? [[String: Any]])
        #expect(attendees.first?["email"] as? String == "priya.sharma@nexusai.com")
        // responseStatus not set on the write -> omitted.
        #expect(attendees.first?["responseStatus"] == nil)
    }

    @Test("EventPatchRequest with only attendees emits just that key")
    func encodePatch() throws {
        let patch = EventPatchRequest(attendees: [
            EventAttendee(email: "alex@nexusai.com", responseStatus: .accepted),
        ])
        let data = try JSONCoding.makeEncoder().encode(patch)
        let obj = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(obj["summary"] == nil)
        #expect(obj["start"] == nil)
        let attendees = try #require(obj["attendees"] as? [[String: Any]])
        #expect(attendees.first?["email"] as? String == "alex@nexusai.com")
        #expect(attendees.first?["responseStatus"] as? String == "accepted")
    }

    @Test("FreeBusyRequest encodes items as id objects")
    func encodeFreeBusy() throws {
        let req = FreeBusyRequest(
            timeMin: "2026-06-22T00:00:00Z",
            timeMax: "2026-06-23T00:00:00Z",
            items: [.init(id: "primary"), .init(id: "team-alex@nexusai.com")],
            timeZone: "UTC"
        )
        let data = try JSONCoding.makeEncoder().encode(req)
        let obj = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(obj["timeMin"] as? String == "2026-06-22T00:00:00Z")
        let items = try #require(obj["items"] as? [[String: Any]])
        #expect(items.count == 2)
        #expect(items.first?["id"] as? String == "primary")
        // Unset expansion limits omitted.
        #expect(obj["groupExpansionMax"] == nil)
    }
}

@Suite("Calendar freeBusy decoding")
struct CalendarFreeBusyDecodeTests {
    let json = """
    {
      "kind": "calendar#freeBusy",
      "timeMin": "2026-06-22T00:00:00Z",
      "timeMax": "2026-06-23T00:00:00Z",
      "calendars": {
        "primary": {
          "busy": [ { "start": "2026-06-22T10:00:00Z", "end": "2026-06-22T12:00:00Z" } ]
        },
        "team-alex@nexusai.com": {
          "errors": [ { "domain": "global", "reason": "notFound" } ],
          "busy": []
        }
      }
    }
    """

    @Test("decodes busy intervals keyed by requested id")
    func decodesFreeBusy() throws {
        let resp = try JSONCoding.makeDecoder().decode(FreeBusyResponse.self, from: Data(json.utf8))
        #expect(resp.kind == "calendar#freeBusy")
        #expect(resp.timeMinDate != nil)
        let calendars = try #require(resp.calendars)
        let primary = try #require(calendars["primary"])
        #expect(primary.busy?.count == 1)
        #expect(primary.busy?.first?.startDate != nil)
        #expect(primary.errors == nil)
    }

    @Test("error calendar surfaces notFound with empty busy")
    func errorCalendar() throws {
        let resp = try JSONCoding.makeDecoder().decode(FreeBusyResponse.self, from: Data(json.utf8))
        let team = try #require(resp.calendars?["team-alex@nexusai.com"])
        #expect(team.busy?.isEmpty == true)
        #expect(team.errors?.first?.reason == "notFound")
    }
}
