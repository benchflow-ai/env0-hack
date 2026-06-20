import Foundation

/// A point in time on an event: either a timed slot (`dateTime` + `timeZone`)
/// or an all-day slot (`date`). Exactly one of `dateTime`/`date` is populated.
///
/// `Encodable` so it can be sent in create/patch bodies. The raw wire strings
/// are kept verbatim; parsed `Date` values are exposed via computed properties
/// using ``DateParsing`` (rfc3339 for `dateTime`, calendarDay for all-day `date`).
public struct EventDateTime: Decodable, Encodable, Sendable {
    public let dateTime: String?
    public let date: String?
    public let timeZone: String?

    public init(dateTime: String? = nil, date: String? = nil, timeZone: String? = nil) {
        self.dateTime = dateTime
        self.date = date
        self.timeZone = timeZone
    }

    /// Parsed timed value (RFC3339). Nil for all-day events.
    public var dateTimeDate: Date? { DateParsing.rfc3339(dateTime) }

    /// Parsed all-day value (`YYYY-MM-DD` at UTC midnight). Nil for timed events.
    public var dateDate: Date? { DateParsing.calendarDay(date) }

    /// The effective start/end instant regardless of timed vs all-day.
    public var resolvedDate: Date? { dateTimeDate ?? dateDate }
}

/// Lifecycle status of an event.
public enum EventStatus: String, Decodable, Sendable {
    case confirmed
    case tentative
    case cancelled
    case unknown

    public init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = EventStatus(rawValue: raw) ?? .unknown
    }
}

/// An attendee's RSVP state.
public enum AttendeeResponseStatus: String, Decodable, Encodable, Sendable {
    case needsAction
    case accepted
    case declined
    case tentative
    case unknown

    public init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = AttendeeResponseStatus(rawValue: raw) ?? .unknown
    }
}

/// One invitee on an event. `Encodable` so the full attendee array can be
/// rewritten for RSVP / patch.
public struct EventAttendee: Decodable, Encodable, Sendable {
    public let email: String
    public let responseStatus: AttendeeResponseStatus?
    public let displayName: String?
    public let organizer: Bool?
    public let optional: Bool?
    /// The wire `self` flag (is this attendee the acting user). Renamed to
    /// `isSelf` so it never shadows the instance `self`.
    public let isSelf: Bool?

    private enum CodingKeys: String, CodingKey {
        case email, responseStatus, displayName, organizer, optional
        case isSelf = "self"
    }

    public init(
        email: String,
        responseStatus: AttendeeResponseStatus? = nil,
        displayName: String? = nil,
        organizer: Bool? = nil,
        optional: Bool? = nil,
        isSelf: Bool? = nil
    ) {
        self.email = email
        self.responseStatus = responseStatus
        self.displayName = displayName
        self.organizer = organizer
        self.optional = optional
        self.isSelf = isSelf
    }
}

/// Creator / organizer of an event.
public struct EventActor: Decodable, Sendable {
    public let email: String?
    public let displayName: String?
    public let isSelf: Bool?

    private enum CodingKeys: String, CodingKey {
        case email, displayName
        case isSelf = "self"
    }
}

/// A reminder override (`{ method, minutes }`), shared by events and calendars.
public struct EventReminderOverride: Decodable, Sendable {
    public let method: String?
    public let minutes: Int?
}

/// Reminder configuration on an event (mock always returns `{useDefault:true}`).
public struct EventReminders: Decodable, Sendable {
    public let useDefault: Bool?
    public let overrides: [EventReminderOverride]?
}

/// A calendar event (`calendar#event` = `EventResource`).
///
/// Sparse fields are optional; `created`/`updated` keep the raw RFC3339 strings
/// and expose parsed `Date` values via computed properties.
public struct CalendarEvent: Decodable, Sendable {
    public let kind: String?
    public let etag: String?
    public let id: String
    public let status: EventStatus?
    public let htmlLink: String?
    public let created: String?
    public let updated: String?
    public let summary: String?
    public let description: String?
    public let location: String?
    public let iCalUID: String?
    public let sequence: Int?
    public let start: EventDateTime?
    public let end: EventDateTime?
    public let attendees: [EventAttendee]?
    public let creator: EventActor?
    public let organizer: EventActor?
    public let reminders: EventReminders?
    public let eventType: String?
    public let recurrence: [String]?
    public let recurringEventId: String?
    public let originalStartTime: EventDateTime?

    /// Parsed creation instant (RFC3339).
    public var createdDate: Date? { DateParsing.rfc3339(created) }

    /// Parsed last-modified instant (RFC3339).
    public var updatedDate: Date? { DateParsing.rfc3339(updated) }
}

/// Envelope for `events.list` (`calendar#events`).
public struct EventList: Decodable, Sendable {
    public let kind: String?
    public let etag: String?
    public let summary: String?
    public let description: String?
    public let timeZone: String?
    public let updated: String?
    public let accessRole: CalendarAccessRole?
    public let defaultReminders: [EventReminderOverride]?
    public let nextPageToken: String?
    public let nextSyncToken: String?
    /// Optional per the list-envelope convention; the service exposes `?? []`.
    public let items: [CalendarEvent]?

    /// Parsed last-modified instant (RFC3339).
    public var updatedDate: Date? { DateParsing.rfc3339(updated) }
}
