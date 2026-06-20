import SwiftUI
import Env0Kit

/// Root view of the Calendar tab. Embedded by `RootView` inside a
/// `NavigationStack`, so it adds no stack of its own.
///
/// On load it resolves the primary calendar and lists its upcoming events,
/// grouped by day. Tapping an event drills into `EventDetailView`; the toolbar
/// "+" opens an add-event sheet.
struct CalendarView: View {
    @Environment(AppSettings.self) private var settings
    @State private var store = CalendarStore()
    @State private var showingAddEvent = false

    var body: some View {
        LoadableView(store.state, retry: { Task { await store.load(settings.suite) } }) { days in
            content(days)
        }
        .navigationTitle("Calendar")
        .navigationDestination(for: String.self) { eventId in
            EventDetailView(eventId: eventId, store: store)
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showingAddEvent = true
                } label: {
                    Label("Add Event", systemImage: "plus")
                }
                .disabled(store.primaryCalendarId == nil)
            }
        }
        .sheet(isPresented: $showingAddEvent) {
            AddEventSheet(store: store)
        }
        .task { await store.load(settings.suite) }
        .refreshable { await store.load(settings.suite) }
    }

    @ViewBuilder
    private func content(_ days: [EventDay]) -> some View {
        if days.isEmpty {
            ContentUnavailableView(
                "No Upcoming Events",
                systemImage: "calendar",
                description: Text("You're all clear. Pull to refresh or add an event.")
            )
        } else {
            List {
                ForEach(days) { day in
                    Section(CalendarFormatting.dayHeader(day)) {
                        ForEach(day.events, id: \.id) { event in
                            NavigationLink(value: event.id) {
                                EventRow(event: event)
                            }
                        }
                    }
                }
            }
            .listStyle(.insetGrouped)
        }
    }
}

/// A single event row: summary, time range, location, and attendee count.
private struct EventRow: View {
    let event: CalendarEvent

    private var attendeeCount: Int { event.attendees?.count ?? 0 }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Text(event.summary ?? "(no title)")
                .font(.headline)
                .lineLimit(2)

            Label(CalendarFormatting.timeRange(for: event), systemImage: "clock")
                .font(.subheadline)
                .foregroundStyle(Theme.calendar)

            if let location = event.location, !location.isEmpty {
                Label(location, systemImage: "mappin.and.ellipse")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            if attendeeCount > 0 {
                Label(
                    "^[\(attendeeCount) guest](inflect: true)",
                    systemImage: "person.2"
                )
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, Theme.Spacing.xs)
    }
}
