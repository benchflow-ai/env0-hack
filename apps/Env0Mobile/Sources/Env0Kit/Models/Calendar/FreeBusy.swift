import Foundation

/// Body for `freebusy.query`. `timeMin`/`timeMax`/`items` are required; the
/// calendar ids in `items` may be real ids or the `primary` alias.
public struct FreeBusyRequest: Encodable, Sendable {
    /// One calendar to query, by id (or `primary`).
    public struct Item: Encodable, Sendable {
        public let id: String

        public init(id: String) {
            self.id = id
        }
    }

    public var timeMin: String
    public var timeMax: String
    public var timeZone: String?
    public var items: [Item]
    public var groupExpansionMax: Int?
    public var calendarExpansionMax: Int?

    public init(
        timeMin: String,
        timeMax: String,
        items: [Item],
        timeZone: String? = nil,
        groupExpansionMax: Int? = nil,
        calendarExpansionMax: Int? = nil
    ) {
        self.timeMin = timeMin
        self.timeMax = timeMax
        self.items = items
        self.timeZone = timeZone
        self.groupExpansionMax = groupExpansionMax
        self.calendarExpansionMax = calendarExpansionMax
    }
}

/// A single busy interval. `start`/`end` keep the raw RFC3339 strings and
/// expose parsed `Date` values.
public struct FreeBusyInterval: Decodable, Sendable {
    public let start: String?
    public let end: String?

    public var startDate: Date? { DateParsing.rfc3339(start) }
    public var endDate: Date? { DateParsing.rfc3339(end) }
}

/// A diagnostic error returned for a calendar that could not be queried
/// (e.g. `notFound`).
public struct FreeBusyError: Decodable, Sendable {
    public let domain: String?
    public let reason: String?
}

/// Busy/error data for one queried calendar.
public struct FreeBusyCalendar: Decodable, Sendable {
    /// Always an array (possibly empty).
    public let busy: [FreeBusyInterval]?
    /// Present only on failure.
    public let errors: [FreeBusyError]?
}

/// Response for `freebusy.query` (`calendar#freeBusy`).
///
/// `calendars` is keyed by the exact id string passed in the request (so
/// `"primary"` stays `"primary"`, not the resolved calendar id).
public struct FreeBusyResponse: Decodable, Sendable {
    public let kind: String?
    public let timeMin: String?
    public let timeMax: String?
    public let calendars: [String: FreeBusyCalendar]?

    public var timeMinDate: Date? { DateParsing.rfc3339(timeMin) }
    public var timeMaxDate: Date? { DateParsing.rfc3339(timeMax) }
}
