import Foundation

/// Body for `events.insert` (create) and `events.update` (full replace).
///
/// `start`/`end` are required objects; `summary`/`description`/`location`
/// default to `""` server-side when omitted. Only the request types are
/// `Encodable`. The encoder omits nil keys.
public struct EventWriteRequest: Encodable, Sendable {
    public var summary: String?
    public var description: String?
    public var location: String?
    public var start: EventDateTime
    public var end: EventDateTime
    public var attendees: [EventAttendee]?
    public var recurrence: [String]?
    public var iCalUID: String?
    public var status: String?

    public init(
        summary: String? = nil,
        description: String? = nil,
        location: String? = nil,
        start: EventDateTime,
        end: EventDateTime,
        attendees: [EventAttendee]? = nil,
        recurrence: [String]? = nil,
        iCalUID: String? = nil,
        status: String? = nil
    ) {
        self.summary = summary
        self.description = description
        self.location = location
        self.start = start
        self.end = end
        self.attendees = attendees
        self.recurrence = recurrence
        self.iCalUID = iCalUID
        self.status = status
    }
}

/// Body for `events.patch` (partial update). Every field optional; only the
/// supplied fields change. Nil keys are omitted by the encoder, so unset fields
/// are left untouched on the server.
public struct EventPatchRequest: Encodable, Sendable {
    public var summary: String?
    public var description: String?
    public var location: String?
    public var status: String?
    public var start: EventDateTime?
    public var end: EventDateTime?
    public var attendees: [EventAttendee]?
    public var recurrence: [String]?

    public init(
        summary: String? = nil,
        description: String? = nil,
        location: String? = nil,
        status: String? = nil,
        start: EventDateTime? = nil,
        end: EventDateTime? = nil,
        attendees: [EventAttendee]? = nil,
        recurrence: [String]? = nil
    ) {
        self.summary = summary
        self.description = description
        self.location = location
        self.status = status
        self.start = start
        self.end = end
        self.attendees = attendees
        self.recurrence = recurrence
    }
}
