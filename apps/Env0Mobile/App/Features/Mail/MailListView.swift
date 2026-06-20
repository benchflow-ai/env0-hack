import SwiftUI
import Env0Kit

/// The Mail tab's root view: a searchable list of Gmail threads. Embedded by
/// `RootView` inside a `NavigationStack`, so it sets a title and a
/// `.navigationDestination` but never wraps itself in a stack.
///
/// The list is driven by the cheap `threads.list` stubs (id + snippet); each row
/// then lazily fetches its thread's detail to surface the latest message's
/// subject, sender, date and unread state. Tapping a row opens the full thread.
struct MailListView: View {
    @Environment(AppSettings.self) private var settings
    @State private var store = MailStore()
    @State private var isComposing = false

    var body: some View {
        @Bindable var store = store
        LoadableView(store.state, retry: { Task { await store.load(settings.suite) } }) { threads in
            content(threads)
        }
        .navigationTitle("Mail")
        .searchable(text: $store.query, prompt: "Search mail")
        .onSubmit(of: .search) {
            Task { await store.load(settings.suite) }
        }
        .navigationDestination(for: String.self) { threadId in
            ThreadDetailView(threadId: threadId)
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    isComposing = true
                } label: {
                    Label("Compose", systemImage: "square.and.pencil")
                }
            }
        }
        .sheet(isPresented: $isComposing) {
            ComposeView()
        }
        .task { await store.load(settings.suite) }
        .refreshable { await store.load(settings.suite) }
    }

    @ViewBuilder
    private func content(_ threads: [GmailThread]) -> some View {
        if threads.isEmpty {
            ContentUnavailableView(
                store.query.isEmpty ? "No Mail" : "No Results",
                systemImage: "tray",
                description: Text(
                    store.query.isEmpty
                        ? "Your inbox is empty."
                        : "No threads match \"\(store.query)\"."
                )
            )
        } else {
            List(threads, id: \.id) { thread in
                NavigationLink(value: thread.id) {
                    MailThreadRow(thread: thread)
                }
            }
            .listStyle(.plain)
        }
    }
}

/// One row in the thread list. Shows the cheap `GmailThread.snippet` immediately,
/// then lazily loads the thread detail to enrich the row with the latest
/// message's subject, sender, relative date and an unread indicator.
private struct MailThreadRow: View {
    @Environment(AppSettings.self) private var settings
    let thread: GmailThread

    /// Latest-message metadata, filled in once the detail loads.
    @State private var subject: String?
    @State private var sender: String?
    @State private var date: Date?
    @State private var isUnread = false
    @State private var hasAttachment = false
    @State private var didLoad = false

    var body: some View {
        HStack(alignment: .top, spacing: Theme.Spacing.m) {
            // Unread indicator: a filled dot when the thread's first message is unread.
            Circle()
                .fill(isUnread ? Theme.mail : .clear)
                .frame(width: 8, height: 8)
                .padding(.top, 6)

            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                HStack {
                    Text(sender ?? "Loading…")
                        .font(.subheadline)
                        .fontWeight(isUnread ? .semibold : .regular)
                        .lineLimit(1)
                    if hasAttachment {
                        Image(systemName: "paperclip")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    if let date {
                        Text(date, format: .relative(presentation: .named))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                Text(subject ?? "")
                    .font(.subheadline)
                    .fontWeight(isUnread ? .medium : .regular)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                Text(thread.snippet.isEmpty ? "(no preview)" : thread.snippet)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, Theme.Spacing.xs)
        .task(id: thread.id) {
            guard !didLoad else { return }
            await enrich()
        }
    }

    /// Fetch the full thread once to populate the row's latest-message fields.
    private func enrich() async {
        do {
            let detail = try await settings.suite.gmail.getThread(id: thread.id)
            let messages = detail.messages ?? []
            // Unread is keyed on the thread's *first* message per the spec.
            isUnread = messages.first?.labelIds?.contains("UNREAD") ?? false
            if let latest = messages.last {
                subject = latest.subject ?? "(no subject)"
                sender = latest.from.map(displayName) ?? "Unknown sender"
                date = latest.bestDate
                hasAttachment = latest.hasAttachment
            }
            didLoad = true
        } catch {
            // Leave the snippet visible; the row stays usable even if enrich fails.
            sender = sender ?? ""
            subject = subject ?? ""
        }
    }

    /// Pull a human display name out of an RFC2822 `From` header
    /// (`"Jane Doe <jane@x.com>"` → `Jane Doe`).
    private func displayName(_ from: String) -> String {
        if let open = from.firstIndex(of: "<") {
            let name = from[..<open].trimmingCharacters(in: .whitespaces)
                .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
            if !name.isEmpty { return name }
        }
        return from
    }
}
