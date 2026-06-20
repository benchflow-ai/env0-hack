import SwiftUI
import Env0Kit

/// Detail screen for one event, reached via `.navigationDestination(for: String.self)`
/// (the route payload is the event id).
///
/// Loads the event with `calendar.getEvent` (reusing the store's resolved primary
/// calendar id), then shows summary, time, location, description, organizer, and
/// the attendee list with each `responseStatus`. If the acting user is an
/// attendee, RSVP buttons (Going / Maybe / No) patch their status via
/// `calendar.rsvp`.
struct EventDetailView: View {
    @Environment(AppSettings.self) private var settings
    let eventId: String
    let store: CalendarStore

    var body: some View {
        LoadableView(
            store.detailState(for: eventId),
            retry: { Task { await store.loadEvent(settings.suite, eventId: eventId) } }
        ) { event in
            detail(event)
        }
        .navigationTitle("Event")
        .navigationBarTitleDisplayMode(.inline)
        .task { await store.loadEvent(settings.suite, eventId: eventId) }
    }

    @ViewBuilder
    private func detail(_ event: CalendarEvent) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.l) {
                header(event)
                if let selfAttendee = event.selfAttendee {
                    rsvpSection(event: event, selfAttendee: selfAttendee)
                }
                if let description = event.description, !description.isEmpty {
                    descriptionSection(description)
                }
                if let organizer = event.organizer {
                    organizerSection(organizer)
                }
                if let attendees = event.attendees, !attendees.isEmpty {
                    attendeesSection(attendees)
                }
            }
            .padding(Theme.Spacing.l)
        }
    }

    // MARK: - Sections

    @ViewBuilder
    private func header(_ event: CalendarEvent) -> some View {
        GlassCard {
            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                Text(event.summary ?? "(no title)")
                    .font(.title2.bold())

                Label(CalendarFormatting.detailDateTime(for: event), systemImage: "clock")
                    .font(.subheadline)
                    .foregroundStyle(Theme.calendar)

                if let location = event.location, !location.isEmpty {
                    Label(location, systemImage: "mappin.and.ellipse")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private func rsvpSection(event: CalendarEvent, selfAttendee: EventAttendee) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            sectionTitle("Your RSVP")

            let current = selfAttendee.responseStatus ?? .needsAction
            Label(current.label, systemImage: current.systemImage)
                .font(.subheadline)
                .foregroundStyle(current.tint)

            HStack(spacing: Theme.Spacing.s) {
                rsvpButton(.accepted, current: current, event: event, email: selfAttendee.email)
                rsvpButton(.tentative, current: current, event: event, email: selfAttendee.email)
                rsvpButton(.declined, current: current, event: event, email: selfAttendee.email)
            }
            .disabled(store.isRSVPInFlight(event.id))

            if store.isRSVPInFlight(event.id) {
                ProgressView().controlSize(.small)
            }
        }
    }

    @ViewBuilder
    private func rsvpButton(
        _ status: AttendeeResponseStatus,
        current: AttendeeResponseStatus,
        event: CalendarEvent,
        email: String
    ) -> some View {
        let button = Button {
            Task {
                await store.rsvp(
                    settings.suite,
                    eventId: event.id,
                    status: status,
                    attendeeEmail: email
                )
            }
        } label: {
            Label(status.label, systemImage: status.systemImage)
                .frame(maxWidth: .infinity)
        }
        .tint(status.tint)

        // The selected status is prominent; the others are plain glass. The two
        // glass styles are distinct concrete types, so branch the modifier.
        if status == current {
            button.buttonStyle(.glassProminent)
        } else {
            button.buttonStyle(.glass)
        }
    }

    @ViewBuilder
    private func descriptionSection(_ description: String) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            sectionTitle("Notes")
            Text(description)
                .font(.body)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(Theme.Spacing.l)
                .glassCard()
        }
    }

    @ViewBuilder
    private func organizerSection(_ organizer: EventActor) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            sectionTitle("Organizer")
            HStack(spacing: Theme.Spacing.m) {
                Image(systemName: "person.crop.circle.badge.checkmark")
                    .foregroundStyle(Theme.calendar)
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text(CalendarFormatting.displayName(organizer))
                        .font(.subheadline.weight(.medium))
                    if let email = organizer.email {
                        Text(email)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
            }
            .padding(Theme.Spacing.l)
            .glassCard()
        }
    }

    @ViewBuilder
    private func attendeesSection(_ attendees: [EventAttendee]) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            sectionTitle("^[\(attendees.count) Guest](inflect: true)")
            VStack(spacing: 0) {
                ForEach(Array(attendees.enumerated()), id: \.offset) { index, attendee in
                    attendeeRow(attendee)
                    if index < attendees.count - 1 {
                        Divider()
                    }
                }
            }
            .padding(Theme.Spacing.l)
            .glassCard()
        }
    }

    @ViewBuilder
    private func attendeeRow(_ attendee: EventAttendee) -> some View {
        let status = attendee.responseStatus ?? .needsAction
        HStack(spacing: Theme.Spacing.m) {
            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                HStack(spacing: Theme.Spacing.xs) {
                    Text(CalendarFormatting.displayName(attendee))
                        .font(.subheadline)
                    if attendee.isSelf == true {
                        Text("You")
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, Theme.Spacing.s)
                            .padding(.vertical, 2)
                            .glassEffect(.regular, in: .capsule)
                    }
                    if attendee.optional == true {
                        Text("Optional")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }
                if attendee.displayName?.isEmpty == false {
                    Text(attendee.email)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            Label(status.label, systemImage: status.systemImage)
                .labelStyle(.iconOnly)
                .foregroundStyle(status.tint)
                .help(status.label)
        }
        .padding(.vertical, Theme.Spacing.s)
    }

    @ViewBuilder
    private func sectionTitle(_ text: LocalizedStringKey) -> some View {
        Text(text)
            .font(.headline)
            .foregroundStyle(.secondary)
    }
}
