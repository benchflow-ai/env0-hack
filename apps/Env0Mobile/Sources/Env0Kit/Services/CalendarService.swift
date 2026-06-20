import Foundation

/// Typed client for the env-0 mock Google Calendar service (`/calendar/v3`).
///
/// Mirrors the real Calendar v3 wire format, so it points at a running env-0
/// instance (port 9003 / `CALENDAR_URL`) instead of `www.googleapis.com`.
/// Build it with the calendar-scoped ``Env0APIClient`` (its `baseURL` is the
/// service root; this type adds the `/calendar/v3` path prefix).
public struct CalendarService: Sendable {
    private let client: any Env0Requesting

    public init(client: any Env0Requesting) {
        self.client = client
    }

    private static let prefix = "/calendar/v3"

    // MARK: - calendarList

    /// List the user's calendars (`calendarList.list`).
    /// - Parameters:
    ///   - userId: the acting user; `"me"` resolves from the request identity.
    ///   - maxResults: page size (1–250).
    ///   - pageToken: numeric offset token from a prior `nextPageToken`.
    ///   - minAccessRole: minimum access role to include.
    ///   - showHidden: include hidden calendars.
    ///   - syncToken: incremental sync token.
    public func listCalendars(
        userId: String = "me",
        maxResults: Int? = nil,
        pageToken: String? = nil,
        minAccessRole: String? = nil,
        showHidden: Bool? = nil,
        syncToken: String? = nil
    ) async throws -> CalendarList {
        let query: [URLQueryItem] = [
            URLQueryItem.optional("maxResults", maxResults.map(String.init)),
            URLQueryItem.optional("pageToken", pageToken),
            URLQueryItem.optional("minAccessRole", minAccessRole),
            URLQueryItem.optional("showHidden", showHidden.map { $0 ? "true" : "false" }),
            URLQueryItem.optional("syncToken", syncToken),
        ].compactMap { $0 }
        let endpoint = Endpoint(
            "\(Self.prefix)/users/\(userId)/calendarList",
            method: .get,
            query: query
        )
        return try await client.get(CalendarList.self, endpoint)
    }

    // MARK: - events

    /// List events on a calendar (`events.list`).
    /// - Parameters:
    ///   - calendarId: a calendar id or the `"primary"` alias.
    ///   - timeMin: lower bound (RFC3339); matches events ending at/after it.
    ///   - timeMax: upper bound (RFC3339); must be greater than `timeMin`.
    ///   - q: substring match on summary/description.
    ///   - singleEvents: expand recurring masters into instances.
    ///   - orderBy: `"startTime"` or `"updated"`.
    ///   - maxResults: page size (1–2500).
    ///   - pageToken: numeric offset token.
    ///   - showDeleted: include cancelled events.
    ///   - syncToken: incremental sync token.
    public func listEvents(
        calendarId: String,
        timeMin: String? = nil,
        timeMax: String? = nil,
        q: String? = nil,
        singleEvents: Bool? = nil,
        orderBy: String? = nil,
        maxResults: Int? = nil,
        pageToken: String? = nil,
        showDeleted: Bool? = nil,
        syncToken: String? = nil
    ) async throws -> EventList {
        let query: [URLQueryItem] = [
            URLQueryItem.optional("timeMin", timeMin),
            URLQueryItem.optional("timeMax", timeMax),
            URLQueryItem.optional("q", q),
            URLQueryItem.optional("singleEvents", singleEvents.map { $0 ? "true" : "false" }),
            URLQueryItem.optional("orderBy", orderBy),
            URLQueryItem.optional("maxResults", maxResults.map(String.init)),
            URLQueryItem.optional("pageToken", pageToken),
            URLQueryItem.optional("showDeleted", showDeleted.map { $0 ? "true" : "false" }),
            URLQueryItem.optional("syncToken", syncToken),
        ].compactMap { $0 }
        let endpoint = Endpoint(
            "\(Self.prefix)/calendars/\(calendarId)/events",
            method: .get,
            query: query
        )
        return try await client.get(EventList.self, endpoint)
    }

    /// Fetch a single event (`events.get`). `eventId` may be a base id or a
    /// recurring-instance id (`evt_..._YYYYMMDDTHHMMSSZ`).
    public func getEvent(calendarId: String, eventId: String) async throws -> CalendarEvent {
        let endpoint = Endpoint(
            "\(Self.prefix)/calendars/\(calendarId)/events/\(eventId)",
            method: .get
        )
        return try await client.get(CalendarEvent.self, endpoint)
    }

    /// Create an event (`events.insert`). `start`/`end` are required and `end`
    /// must be strictly after `start`. Returns the full created event.
    public func createEvent(
        calendarId: String,
        event: EventWriteRequest
    ) async throws -> CalendarEvent {
        let body = try JSONCoding.makeEncoder().encode(event)
        let endpoint = Endpoint(
            "\(Self.prefix)/calendars/\(calendarId)/events",
            method: .post,
            body: body
        )
        return try await client.get(CalendarEvent.self, endpoint)
    }

    /// Partially update an event (`events.patch`). Only the fields set on
    /// `patch` change. Returns the full updated event.
    public func updateEvent(
        calendarId: String,
        eventId: String,
        patch: EventPatchRequest
    ) async throws -> CalendarEvent {
        let body = try JSONCoding.makeEncoder().encode(patch)
        let endpoint = Endpoint(
            "\(Self.prefix)/calendars/\(calendarId)/events/\(eventId)",
            method: .patch,
            body: body
        )
        return try await client.get(CalendarEvent.self, endpoint)
    }

    /// Delete an event (`events.delete`). Hard-deletes the row; returns nothing.
    public func deleteEvent(calendarId: String, eventId: String) async throws {
        let endpoint = Endpoint(
            "\(Self.prefix)/calendars/\(calendarId)/events/\(eventId)",
            method: .delete
        )
        try await client.run(endpoint)
    }

    // MARK: - RSVP

    /// Respond to (RSVP) an event by flipping one attendee's `responseStatus`.
    ///
    /// There is no dedicated RSVP endpoint: as with the real Calendar API this
    /// is an `events.patch` that rewrites the whole `attendees` array. This
    /// helper fetches the event, replaces the matching attendee's status (or
    /// appends a new attendee if `attendeeEmail` is absent), and patches the
    /// full list back. `attendeeEmail` defaults to the account owner so the
    /// common "change my own RSVP" case is one call.
    /// - Returns: the updated event with the new attendee statuses.
    @discardableResult
    public func rsvp(
        calendarId: String,
        eventId: String,
        responseStatus: AttendeeResponseStatus,
        attendeeEmail: String
    ) async throws -> CalendarEvent {
        let event = try await getEvent(calendarId: calendarId, eventId: eventId)
        var attendees = event.attendees ?? []
        let lowered = attendeeEmail.lowercased()
        if let index = attendees.firstIndex(where: { $0.email.lowercased() == lowered }) {
            let existing = attendees[index]
            attendees[index] = EventAttendee(
                email: existing.email,
                responseStatus: responseStatus,
                displayName: existing.displayName,
                organizer: existing.organizer,
                optional: existing.optional,
                isSelf: existing.isSelf
            )
        } else {
            attendees.append(EventAttendee(email: attendeeEmail, responseStatus: responseStatus))
        }
        let patch = EventPatchRequest(attendees: attendees)
        return try await updateEvent(calendarId: calendarId, eventId: eventId, patch: patch)
    }

    // MARK: - freeBusy

    /// Query busy intervals across calendars (`freebusy.query`). The response's
    /// `calendars` map is keyed by the exact id strings passed in `request.items`.
    public func freeBusy(_ request: FreeBusyRequest) async throws -> FreeBusyResponse {
        let body = try JSONCoding.makeEncoder().encode(request)
        let endpoint = Endpoint(
            "\(Self.prefix)/freeBusy",
            method: .post,
            body: body
        )
        return try await client.get(FreeBusyResponse.self, endpoint)
    }
}
