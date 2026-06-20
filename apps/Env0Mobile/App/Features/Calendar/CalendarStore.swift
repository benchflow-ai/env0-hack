import SwiftUI
import Env0Kit

/// Store for the Calendar tab. Loads the user's calendar list, picks the primary
/// calendar, then lists its upcoming events grouped by day. Also drives the
/// event-detail load + RSVP, reusing the chosen `calendarId` throughout.
///
/// Follows the feature-store pattern: `@MainActor @Observable`, `Loadable`
/// sub-state, and load methods that TAKE THE SUITE AS A PARAMETER (never
/// constructing `Env0Suite` themselves).
@MainActor
@Observable
final class CalendarStore {
    /// Upcoming events grouped into ascending days. Populated by `load`.
    var state: Loadable<[EventDay]> = .idle

    /// The calendar we resolved as primary on the last successful load. Detail
    /// and RSVP reuse this id so every call targets the same calendar.
    private(set) var primaryCalendarId: String?

    /// Human label for the primary calendar (its summary), shown in the title.
    private(set) var primaryTitle: String?

    /// Per-event detail state, keyed by event id. Detail views read their own
    /// slice so concurrently open details don't clobber each other.
    var details: [String: Loadable<CalendarEvent>] = [:]

    /// Event ids with an RSVP request in flight (to disable buttons / show spinner).
    private(set) var rsvpInFlight: Set<String> = []

    // MARK: - List

    /// Load the primary calendar's upcoming events.
    ///
    /// 1. `calendar.listCalendars()` → pick the primary (first `primary == true`,
    ///    else the first entry).
    /// 2. `calendar.listEvents(... timeMin: nowISO8601, singleEvents: true,
    ///    orderBy: "startTime")`.
    /// 3. Group the results by calendar day for the UI.
    func load(_ suite: Env0Suite) async {
        state = .loading
        do {
            let list = try await suite.calendar.listCalendars()
            let entries = list.items ?? []
            guard let primary = entries.first(where: { $0.primary == true }) ?? entries.first else {
                primaryCalendarId = nil
                primaryTitle = nil
                state = .loaded([])
                return
            }
            primaryCalendarId = primary.id
            primaryTitle = primary.summaryOverride ?? primary.summary

            let now = ISO8601DateFormatter().string(from: Date())
            let events = try await suite.calendar.listEvents(
                calendarId: primary.id,
                timeMin: now,
                singleEvents: true,
                orderBy: "startTime"
            )
            state = .loaded(Self.groupByDay(events.items ?? []))
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    // MARK: - Detail

    /// State for a single event's detail screen.
    func detailState(for eventId: String) -> Loadable<CalendarEvent> {
        details[eventId] ?? .idle
    }

    /// Load one event via `calendar.getEvent`, using the primary calendar id.
    func loadEvent(_ suite: Env0Suite, eventId: String) async {
        guard let calendarId = primaryCalendarId else {
            details[eventId] = .failed("No calendar selected.")
            return
        }
        details[eventId] = .loading
        do {
            let event = try await suite.calendar.getEvent(calendarId: calendarId, eventId: eventId)
            details[eventId] = .loaded(event)
        } catch {
            details[eventId] = .failed(error.localizedDescription)
        }
    }

    // MARK: - RSVP

    /// Flip the current user's RSVP on an event, then refresh the detail.
    ///
    /// `attendeeEmail` is the acting user's email (taken from the `self`-flagged
    /// attendee). On success the updated event the service returns is stored, and
    /// the list is reloaded so any status-derived UI stays in sync.
    func rsvp(
        _ suite: Env0Suite,
        eventId: String,
        status: AttendeeResponseStatus,
        attendeeEmail: String
    ) async {
        guard let calendarId = primaryCalendarId else { return }
        rsvpInFlight.insert(eventId)
        defer { rsvpInFlight.remove(eventId) }
        do {
            let updated = try await suite.calendar.rsvp(
                calendarId: calendarId,
                eventId: eventId,
                responseStatus: status,
                attendeeEmail: attendeeEmail
            )
            details[eventId] = .loaded(updated)
            await load(suite)
        } catch {
            details[eventId] = .failed(error.localizedDescription)
        }
    }

    func isRSVPInFlight(_ eventId: String) -> Bool {
        rsvpInFlight.contains(eventId)
    }

    // MARK: - Create

    /// Build an `EventWriteRequest` from a timed start/end and create it on the
    /// primary calendar, then reload the list.
    func createEvent(
        _ suite: Env0Suite,
        summary: String,
        location: String?,
        start: Date,
        end: Date
    ) async throws {
        guard let calendarId = primaryCalendarId else {
            throw CalendarStoreError.noPrimaryCalendar
        }
        let formatter = ISO8601DateFormatter()
        let request = EventWriteRequest(
            summary: summary,
            location: location?.isEmpty == false ? location : nil,
            start: EventDateTime(dateTime: formatter.string(from: start)),
            end: EventDateTime(dateTime: formatter.string(from: end))
        )
        _ = try await suite.calendar.createEvent(calendarId: calendarId, event: request)
        await load(suite)
    }

    // MARK: - Grouping

    /// Group events into ascending days using each event's resolved start instant.
    /// Events without a resolvable start sort last under a synthetic "Undated" key.
    static func groupByDay(_ events: [CalendarEvent]) -> [EventDay] {
        var calendar = Calendar.current
        calendar.timeZone = .current
        let undatedKey = Date.distantFuture

        let grouped = Dictionary(grouping: events) { event -> Date in
            guard let start = event.start?.resolvedDate else { return undatedKey }
            return calendar.startOfDay(for: start)
        }

        return grouped
            .map { day, items in
                let sortedItems = items.sorted { lhs, rhs in
                    let l = lhs.start?.resolvedDate ?? .distantFuture
                    let r = rhs.start?.resolvedDate ?? .distantFuture
                    return l < r
                }
                return EventDay(day: day, isUndated: day == undatedKey, events: sortedItems)
            }
            .sorted { $0.day < $1.day }
    }
}

enum CalendarStoreError: LocalizedError {
    case noPrimaryCalendar

    var errorDescription: String? {
        switch self {
        case .noPrimaryCalendar: "No primary calendar is available."
        }
    }
}

/// One day's worth of events, the unit the list renders as a section.
struct EventDay: Identifiable, Sendable {
    let day: Date
    let isUndated: Bool
    let events: [CalendarEvent]

    var id: Date { day }
}
