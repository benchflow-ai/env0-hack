import SwiftUI
import Env0Kit

/// Presentation helpers for calendar events: time-range strings, day headers,
/// and small conveniences over the wire models. Kept free of view state so both
/// the list and the detail screen format identically.
enum CalendarFormatting {
    /// "All-day" if the event resolves only from `date`, otherwise a time range
    /// like "9:00 AM – 9:30 AM". Falls back gracefully when an endpoint is missing.
    static func timeRange(for event: CalendarEvent) -> String {
        timeRange(start: event.start, end: event.end)
    }

    static func timeRange(start: EventDateTime?, end: EventDateTime?) -> String {
        let isAllDay = (start?.dateTimeDate == nil) && (start?.dateDate != nil)
        if isAllDay { return "All-day" }

        let startTime = start?.dateTimeDate
        let endTime = end?.dateTimeDate

        switch (startTime, endTime) {
        case let (.some(s), .some(e)):
            return "\(timeFormatter.string(from: s)) – \(timeFormatter.string(from: e))"
        case let (.some(s), .none):
            return timeFormatter.string(from: s)
        case let (.none, .some(e)):
            return "until \(timeFormatter.string(from: e))"
        case (.none, .none):
            return "Time TBD"
        }
    }

    /// Full date + time for the detail screen, e.g. "Sat, Jun 20, 2026 · 9:00 AM – 9:30 AM".
    static func detailDateTime(for event: CalendarEvent) -> String {
        let range = timeRange(for: event)
        guard let start = event.start?.resolvedDate else { return range }
        let day = fullDateFormatter.string(from: start)
        return "\(day) · \(range)"
    }

    /// Section header for a day, e.g. "Today", "Tomorrow", or "Saturday, Jun 20".
    static func dayHeader(_ day: EventDay) -> String {
        if day.isUndated { return "Undated" }
        let calendar = Calendar.current
        if calendar.isDateInToday(day.day) { return "Today" }
        if calendar.isDateInTomorrow(day.day) { return "Tomorrow" }
        return dayHeaderFormatter.string(from: day.day)
    }

    /// Best-effort display name for an attendee or actor.
    static func displayName(_ attendee: EventAttendee) -> String {
        if let name = attendee.displayName, !name.isEmpty { return name }
        return attendee.email
    }

    static func displayName(_ actor: EventActor) -> String {
        if let name = actor.displayName, !name.isEmpty { return name }
        return actor.email ?? "Unknown"
    }

    // MARK: - Formatters

    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .none
        f.timeStyle = .short
        return f
    }()

    private static let fullDateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "EEE, MMM d, yyyy"
        return f
    }()

    private static let dayHeaderFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "EEEE, MMM d"
        return f
    }()
}

extension AttendeeResponseStatus {
    /// Human label for an RSVP status.
    var label: String {
        switch self {
        case .accepted: "Going"
        case .declined: "Not going"
        case .tentative: "Maybe"
        case .needsAction: "No response"
        case .unknown: "Unknown"
        }
    }

    /// SF Symbol communicating the status at a glance.
    var systemImage: String {
        switch self {
        case .accepted: "checkmark.circle.fill"
        case .declined: "xmark.circle.fill"
        case .tentative: "questionmark.circle.fill"
        case .needsAction: "circle.dashed"
        case .unknown: "circle"
        }
    }

    var tint: Color {
        switch self {
        case .accepted: .green
        case .declined: .red
        case .tentative: .orange
        case .needsAction, .unknown: .secondary
        }
    }
}

extension CalendarEvent {
    /// The attendee flagged as the acting user (`self == true`), if any. RSVP is
    /// only offered when this is present, and its email is what we patch.
    var selfAttendee: EventAttendee? {
        attendees?.first { $0.isSelf == true }
    }
}
