import SwiftUI
import Env0Kit

/// A single Gmail thread: every message rendered with the Env0Kit content
/// helpers, plus toolbar actions (star, read/unread, trash) that target the
/// latest message. Reached via `.navigationDestination(for: String.self)` from
/// ``MailListView`` with the thread id as the route payload.
struct ThreadDetailView: View {
    @Environment(AppSettings.self) private var settings
    @Environment(\.dismiss) private var dismiss

    @State private var store: ThreadDetailStore
    @State private var replyRoute: ComposeRoute?

    init(threadId: String) {
        _store = State(initialValue: ThreadDetailStore(threadId: threadId))
    }

    var body: some View {
        LoadableView(store.state, retry: { Task { await store.load(settings.suite) } }) { detail in
            content(detail)
        }
        .navigationTitle(navigationTitle)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { toolbarContent }
        .alert(
            "Action Failed",
            isPresented: Binding(
                get: { store.actionError != nil },
                set: { if !$0 { store.actionError = nil } }
            ),
            presenting: store.actionError
        ) { _ in
            Button("OK", role: .cancel) {}
        } message: { message in
            Text(message)
        }
        .sheet(item: $replyRoute) { route in
            ComposeView(route: route)
        }
        .task {
            await store.load(settings.suite)
            // Opening a thread marks its latest message read, like a real client.
            await store.markRead(settings.suite)
        }
    }

    // MARK: - Title

    private var navigationTitle: String {
        store.latestMessage?.subject ?? "Conversation"
    }

    // MARK: - Body

    @ViewBuilder
    private func content(_ detail: GmailThreadDetail) -> some View {
        let messages = detail.messages ?? []
        if messages.isEmpty {
            ContentUnavailableView(
                "Empty Thread",
                systemImage: "tray",
                description: Text("This conversation has no messages.")
            )
        } else {
            ScrollView {
                LazyVStack(spacing: Theme.Spacing.l) {
                    ForEach(messages, id: \.id) { message in
                        MessageCard(message: message)
                    }
                }
                .padding(Theme.Spacing.l)
            }
            .safeAreaInset(edge: .bottom) {
                replyBar
            }
        }
    }

    // MARK: - Reply bar

    @ViewBuilder
    private var replyBar: some View {
        Button {
            startReply()
        } label: {
            Label("Reply", systemImage: "arrowshape.turn.up.left.fill")
                .frame(maxWidth: .infinity)
        }
        .buttonStyle(.glassProminent)
        .tint(Theme.mail)
        .padding(Theme.Spacing.l)
        .disabled(store.latestMessage == nil)
    }

    // MARK: - Toolbar

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            if store.isMutating {
                ProgressView()
            }
            Button {
                Task { await store.toggleStar(settings.suite) }
            } label: {
                Label(
                    store.isStarred ? "Unstar" : "Star",
                    systemImage: store.isStarred ? "star.fill" : "star"
                )
            }
            .tint(store.isStarred ? .yellow : Theme.mail)
            .disabled(store.latestMessage == nil || store.isMutating)

            Menu {
                Button {
                    Task { await store.toggleRead(settings.suite) }
                } label: {
                    Label(
                        store.isUnread ? "Mark as Read" : "Mark as Unread",
                        systemImage: store.isUnread ? "envelope.open" : "envelope.badge"
                    )
                }
                Button {
                    startReply()
                } label: {
                    Label("Reply", systemImage: "arrowshape.turn.up.left")
                }
                Button(role: .destructive) {
                    Task {
                        if await store.trashLatest(settings.suite) {
                            dismiss()
                        }
                    }
                } label: {
                    Label("Trash", systemImage: "trash")
                }
            } label: {
                Label("More", systemImage: "ellipsis.circle")
            }
            .disabled(store.latestMessage == nil || store.isMutating)
        }
    }

    // MARK: - Actions

    private func startReply() {
        guard let latest = store.latestMessage else { return }
        let to = latest.from ?? ""
        let baseSubject = latest.subject ?? ""
        let subject = baseSubject.lowercased().hasPrefix("re:") ? baseSubject : "Re: \(baseSubject)"
        replyRoute = ComposeRoute(to: to, subject: subject, threadId: store.threadId)
    }
}

/// One message rendered as a glass card: header (sender + date), subject on the
/// first message, then the decoded plain-text body.
private struct MessageCard: View {
    let message: GmailMessage

    var body: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                header
                Divider()
                Text(message.bodyText ?? message.snippet ?? "(no content)")
                    .font(.body)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    @ViewBuilder
    private var header: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            HStack(alignment: .firstTextBaseline) {
                Text(message.from ?? "Unknown sender")
                    .font(.subheadline)
                    .fontWeight(isUnread ? .semibold : .regular)
                    .lineLimit(1)
                Spacer()
                if isUnread {
                    Circle().fill(Theme.mail).frame(width: 8, height: 8)
                }
                if let date = message.bestDate {
                    Text(date, format: .dateTime.month().day().hour().minute())
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            if let to = message.to {
                Text("To: \(to)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            if let subject = message.subject, !subject.isEmpty {
                Text(subject)
                    .font(.headline)
                    .foregroundStyle(.primary)
            }
            if message.hasAttachment {
                Label("Attachment", systemImage: "paperclip")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var isUnread: Bool {
        message.labelIds?.contains("UNREAD") ?? false
    }
}
