import Foundation

/// An entry in the user's calendar list (`calendar#calendarListEntry`).
///
/// Wire format is Google's camelCase JSON; properties map 1:1 to the wire keys.
/// Fields the server omits when empty (`response_model_exclude_none`) are modelled
/// as optionals. `kind`, `etag`, `id`, `summary`, `timeZone`, `accessRole` are
/// always present.
public struct CalendarListEntry: Decodable, Sendable {
    public let kind: String?
    public let etag: String?
    public let id: String
    public let summary: String?
    public let description: String?
    public let location: String?
    public let timeZone: String?
    public let summaryOverride: String?
    public let accessRole: CalendarAccessRole?
    /// Present only when true (omitted for non-primary calendars).
    public let primary: Bool?
    public let selected: Bool?
    public let hidden: Bool?
    public let deleted: Bool?
    public let autoAcceptInvitations: Bool?
    public let colorId: String?
    public let backgroundColor: String?
    public let foregroundColor: String?
    /// Owner email, present only on non-primary calendars.
    public let dataOwner: String?
    public let conferenceProperties: ConferenceProperties?
    public let defaultReminders: [EventReminderOverride]?
    public let notificationSettings: NotificationSettings?
}

/// Access level a user holds on a calendar.
public enum CalendarAccessRole: String, Decodable, Sendable {
    case none
    case freeBusyReader
    case reader
    case writer
    case owner
    case unknown

    public init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = CalendarAccessRole(rawValue: raw) ?? .unknown
    }
}

/// Conferencing capabilities advertised for a calendar.
public struct ConferenceProperties: Decodable, Sendable {
    public let allowedConferenceSolutionTypes: [String]?
}

/// Notification preferences attached to the primary calendar.
public struct NotificationSettings: Decodable, Sendable {
    public struct Notification: Decodable, Sendable {
        public let type: String?
        public let method: String?
    }

    public let notifications: [Notification]?
}

/// Envelope for `calendarList.list` (`calendar#calendarList`).
public struct CalendarList: Decodable, Sendable {
    public let kind: String?
    public let etag: String?
    /// Optional because Google omits empty arrays; the service exposes `?? []`.
    public let items: [CalendarListEntry]?
    public let nextPageToken: String?
    public let nextSyncToken: String?
}
