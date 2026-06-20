import SwiftUI
import Env0Kit

/// Store for the Docs tab's list. Google Docs has no list endpoint, so we list
/// documents through Drive (the real-world pattern): query Drive for files whose
/// `mimeType` is the Google-Docs type, then open each one through the Docs
/// service. Each row is therefore a ``DriveFile`` (carrying `id`, `name`,
/// `modifiedTime`); the document body is only fetched on drill-down.
///
/// Follows the feature-store pattern: `@MainActor @Observable`, `Loadable`
/// sub-state, and load methods that TAKE THE SUITE AS A PARAMETER (never
/// constructing `Env0Suite` themselves).
@MainActor
@Observable
final class DocsStore {
    /// The list of Google Docs (as Drive files), newest-modified first.
    var state: Loadable<[DriveFile]> = .idle

    /// Set while a create is in flight so the toolbar "+" can show progress and
    /// stay disabled.
    var isCreating = false

    /// A transient error from the most recent create, surfaced as an alert.
    var createError: String?

    /// The Drive `q` filter that selects only Google-Docs files.
    private static let docsQuery = "mimeType='application/vnd.google-apps.document'"

    /// A `files(...)` projection rich enough for the row (name + modifiedTime);
    /// without it Drive minimizes each item to `kind,id,name,mimeType`.
    private static let listFields =
        "files(id,name,mimeType,modifiedTime),nextPageToken"

    // MARK: - List

    /// List the user's Google Docs via Drive.
    ///
    /// `drive.listFiles(q:)` with the Google-Docs mimeType filter, ordered by
    /// most-recently-modified. Files missing an `id` (a projected list item can
    /// omit even `id`) are dropped, since rows navigate by id.
    func load(_ suite: Env0Suite) async {
        // Keep prior results visible while reloading so the list doesn't flash.
        if state.value == nil { state = .loading }
        do {
            let list = try await suite.drive.listFiles(
                q: Self.docsQuery,
                fields: Self.listFields,
                orderBy: "modifiedTime desc",
                pageSize: 100
            )
            let docs = (list.files ?? []).filter { $0.id != nil }
            state = .loaded(docs)
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    // MARK: - Create

    /// Create a new, empty document via `docs.createDocument(title:)` and return
    /// its id so the caller can navigate into it. Reloads the list on success so
    /// the new doc appears. Returns `nil` on failure (error stored in
    /// ``createError``).
    func createDocument(_ suite: Env0Suite, title: String) async -> String? {
        let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
        let finalTitle = trimmed.isEmpty ? "Untitled document" : trimmed
        isCreating = true
        defer { isCreating = false }
        do {
            let created = try await suite.docs.createDocument(title: finalTitle)
            await load(suite)
            return created.documentId
        } catch {
            createError = error.localizedDescription
            return nil
        }
    }
}

/// Drives a single ``DocDetailView``: loads one document's body and saves edits.
/// A separate store so each opened document owns its own load/save lifecycle.
///
/// Reading uses `docs.getDocument(documentId:)` and renders
/// ``GDocDocument/title`` + ``GDocDocument/plainText``. Saving uses the
/// web-editor full-content route `docs.saveDocument(documentId:content:)`, then
/// re-reads so the rendered text reflects the server's re-paragraphing.
@MainActor
@Observable
final class DocDetailStore {
    let documentId: String
    var state: Loadable<GDocDocument> = .idle

    /// Set while a save is in flight so the editor can disable controls and show
    /// progress.
    var isSaving = false

    /// A transient error from the most recent save, surfaced as an alert.
    var saveError: String?

    init(documentId: String) {
        self.documentId = documentId
    }

    // MARK: - Load

    /// Load the full document (title + body).
    func load(_ suite: Env0Suite) async {
        if state.value == nil { state = .loading }
        do {
            let document = try await suite.docs.getDocument(documentId: documentId)
            state = .loaded(document)
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    // MARK: - Save

    /// Overwrite the document's entire body with `content` via the web-editor
    /// save route, then reload so the rendered text matches the server. Returns
    /// `true` on success so the view can leave edit mode.
    @discardableResult
    func save(_ suite: Env0Suite, content: String) async -> Bool {
        isSaving = true
        defer { isSaving = false }
        do {
            try await suite.docs.saveDocument(documentId: documentId, content: content)
            await load(suite)
            return true
        } catch {
            saveError = error.localizedDescription
            return false
        }
    }
}
