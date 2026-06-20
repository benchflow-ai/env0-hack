import SwiftUI
import Env0Kit

/// Drives the Mail tab: the searchable thread list plus the currently open
/// thread's detail. Follows the house MV pattern — `@MainActor @Observable`,
/// `Loadable` sub-states, and load methods that take the live `Env0Suite` as a
/// parameter (never constructing one itself).
@MainActor
@Observable
final class MailStore {
    /// The searchable thread list. Each entry is a cheap `GmailThread` stub
    /// (id + snippet); full messages are fetched lazily on navigation.
    var state: Loadable<[GmailThread]> = .idle

    /// The Gmail `q` search string bound to the `.searchable` field.
    var query: String = ""

    // MARK: - Thread list

    /// Reload the thread list for the current ``query`` (cheap stubs only).
    func load(_ suite: Env0Suite) async {
        // Keep prior results visible while reloading so the list doesn't flash.
        if state.value == nil { state = .loading }
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            let list = try await suite.gmail.listThreads(
                query: q.isEmpty ? nil : q,
                maxResults: 50
            )
            state = .loaded(list.threads ?? [])
        } catch {
            state = .failed(error.localizedDescription)
        }
    }
}

/// Drives a single ``ThreadDetailView``. Separate store so each opened thread
/// owns its own load/mutation lifecycle.
@MainActor
@Observable
final class ThreadDetailStore {
    let threadId: String
    var state: Loadable<GmailThreadDetail> = .idle

    /// Set while a toolbar mutation (star/read/trash) is in flight so the UI can
    /// disable the controls and show progress.
    var isMutating = false
    /// A transient error from the most recent mutation, shown as an alert.
    var actionError: String?

    init(threadId: String) {
        self.threadId = threadId
    }

    /// Load the full thread (messages + payloads).
    func load(_ suite: Env0Suite) async {
        if state.value == nil { state = .loading }
        do {
            let detail = try await suite.gmail.getThread(id: threadId)
            state = .loaded(detail)
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    // MARK: - Derived

    /// Messages in the loaded thread, oldest-first as the server returns them.
    var messages: [GmailMessage] {
        state.value?.messages ?? []
    }

    /// The most recent message — the default target for toolbar actions and the
    /// thread the "Reply" affordance answers.
    var latestMessage: GmailMessage? {
        messages.last
    }

    /// Whether the latest message currently carries a given label.
    private func latestHasLabel(_ label: String) -> Bool {
        latestMessage?.labelIds?.contains(label) ?? false
    }

    var isStarred: Bool { latestHasLabel("STARRED") }
    var isUnread: Bool { latestHasLabel("UNREAD") }

    // MARK: - Mutations
    //
    // Each mutation targets the latest message, then reloads the thread so the
    // toolbar reflects the new label set. Errors surface via `actionError`.

    func toggleStar(_ suite: Env0Suite) async {
        guard let id = latestMessage?.id else { return }
        let starred = isStarred
        await mutate(suite) {
            if starred {
                try await suite.gmail.unstar(messageId: id)
            } else {
                try await suite.gmail.star(messageId: id)
            }
        }
    }

    func toggleRead(_ suite: Env0Suite) async {
        guard let id = latestMessage?.id else { return }
        let unread = isUnread
        await mutate(suite) {
            if unread {
                try await suite.gmail.markRead(messageId: id)
            } else {
                try await suite.gmail.markUnread(messageId: id)
            }
        }
    }

    func markRead(_ suite: Env0Suite) async {
        guard let id = latestMessage?.id, isUnread else { return }
        await mutate(suite) {
            try await suite.gmail.markRead(messageId: id)
        }
    }

    /// Trash the latest message. Returns `true` on success so the view can pop.
    @discardableResult
    func trashLatest(_ suite: Env0Suite) async -> Bool {
        guard let id = latestMessage?.id else { return false }
        isMutating = true
        defer { isMutating = false }
        do {
            try await suite.gmail.trash(messageId: id)
            return true
        } catch {
            actionError = error.localizedDescription
            return false
        }
    }

    /// Run a label mutation, then reload so the UI reflects the server state.
    private func mutate(_ suite: Env0Suite, _ action: () async throws -> Void) async {
        isMutating = true
        defer { isMutating = false }
        do {
            try await action()
            await load(suite)
        } catch {
            actionError = error.localizedDescription
        }
    }
}
