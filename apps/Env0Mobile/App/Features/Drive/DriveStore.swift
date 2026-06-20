import SwiftUI
import Env0Kit

/// Drives the Drive tab's file browser: a searchable list of files and folders
/// served by `drive.listFiles`. Follows the house MV pattern — `@MainActor
/// @Observable`, a `Loadable` sub-state, and a `load` method that TAKES THE
/// SUITE AS A PARAMETER (it never constructs an `Env0Suite` itself).
///
/// Each row is a ``DriveFile`` carrying the projected fields the list needs
/// (`id,name,mimeType,modifiedTime,size,owners`); the full resource, content and
/// permissions are only fetched on drill-down by ``FileDetailStore``.
@MainActor
@Observable
final class DriveStore {
    /// The current file/folder listing, most-recently-modified first.
    var state: Loadable<[DriveFile]> = .idle

    /// The free-text query bound to `.searchable`. Turned into a Drive `q`
    /// (`name contains '…'`) on submit.
    var query: String = ""

    /// A rich `files(...)` projection: without it Drive minimizes each item to
    /// `kind,id,name,mimeType`, so rows would lack the owner/modified metadata.
    private static let listFields =
        "files(id,name,mimeType,modifiedTime,createdTime,size,owners,shared),nextPageToken"

    // MARK: - List

    /// Reload the listing for the current ``query``.
    ///
    /// An empty query lists everything (newest-modified first); a non-empty
    /// query becomes a Drive `name contains '…'` filter. Files missing an `id`
    /// (a projected list item can omit even `id`) are dropped, since rows
    /// navigate by id.
    func load(_ suite: Env0Suite) async {
        // Keep prior results visible while reloading so the list doesn't flash.
        if state.value == nil { state = .loading }
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let q = trimmed.isEmpty ? nil : "name contains '\(escape(trimmed))'"
        do {
            let list = try await suite.drive.listFiles(
                q: q,
                fields: Self.listFields,
                orderBy: "modifiedTime desc",
                pageSize: 50
            )
            let files = (list.files ?? []).filter { $0.id != nil }
            state = .loaded(files)
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    /// Escape single quotes so a user query can't break out of the Drive `q`
    /// string literal (`name contains 'O\'Brien'`).
    private func escape(_ value: String) -> String {
        value.replacingOccurrences(of: "'", with: "\\'")
    }
}

/// Drives a single ``FileDetailView``: loads one file's full metadata and its
/// permission list, and lazily previews plain-text content on demand. A separate
/// store so each opened file owns its own load lifecycle.
///
/// Metadata comes from `drive.getFile(fileId:)` (full resource), access from
/// `drive.getFilePermissions(fileId:)`, and a text preview from
/// `drive.downloadFileContent(fileId:)` decoded as UTF-8.
@MainActor
@Observable
final class FileDetailStore {
    let fileId: String

    /// The file's full metadata resource.
    var metadata: Loadable<DriveFile> = .idle

    /// Who has access to the file.
    var permissions: Loadable<[DrivePermission]> = .idle

    /// The decoded text preview, fetched only when the user taps "Preview".
    /// `.idle` until requested.
    var preview: Loadable<String> = .idle

    init(fileId: String) {
        self.fileId = fileId
    }

    // MARK: - Derived

    /// The loaded file, if metadata has resolved.
    var file: DriveFile? { metadata.value }

    /// Whether this resource is a Drive folder (no downloadable content).
    var isFolder: Bool {
        file?.mimeType == DriveMime.folder
    }

    /// Whether this is a Google-native type (Doc/Sheet/Slide/…): no raw bytes to
    /// download, only an export. We surface an export note instead of a preview.
    var isGoogleNative: Bool {
        (file?.mimeType ?? "").hasPrefix("application/vnd.google-apps.")
    }

    /// Whether a raw text preview is offerable: a non-folder, non-Google-native
    /// file whose mime type reads as text-ish.
    var canPreview: Bool {
        guard let mime = file?.mimeType, !isFolder, !isGoogleNative else { return false }
        return DriveMime.isTextual(mime)
    }

    // MARK: - Load

    /// Load metadata and permissions concurrently. Permission failures are
    /// non-fatal — the metadata still renders with an access-load error inline.
    func load(_ suite: Env0Suite) async {
        if metadata.value == nil { metadata = .loading }
        if permissions.value == nil { permissions = .loading }
        async let meta = loadMetadata(suite)
        async let perms = loadPermissions(suite)
        metadata = await meta
        permissions = await perms
    }

    private func loadMetadata(_ suite: Env0Suite) async -> Loadable<DriveFile> {
        do {
            let file = try await suite.drive.getFile(fileId: fileId)
            return .loaded(file)
        } catch {
            return .failed(error.localizedDescription)
        }
    }

    private func loadPermissions(_ suite: Env0Suite) async -> Loadable<[DrivePermission]> {
        do {
            let perms = try await suite.drive.getFilePermissions(
                fileId: fileId,
                fields: "permissions(id,type,role,emailAddress,displayName,domain)"
            )
            return .loaded(perms)
        } catch {
            return .failed(error.localizedDescription)
        }
    }

    // MARK: - Preview

    /// Download the file's raw bytes and decode them as UTF-8 text. Only valid
    /// for previewable (text-ish, non-Google-native) files.
    func loadPreview(_ suite: Env0Suite) async {
        guard canPreview else { return }
        preview = .loading
        do {
            let data = try await suite.drive.downloadFileContent(fileId: fileId)
            let text = String(decoding: data, as: UTF8.self)
            preview = .loaded(text)
        } catch {
            preview = .failed(error.localizedDescription)
        }
    }
}

/// Drive mime-type helpers shared by the store and the views.
enum DriveMime {
    static let folder = "application/vnd.google-apps.folder"
    static let document = "application/vnd.google-apps.document"
    static let spreadsheet = "application/vnd.google-apps.spreadsheet"
    static let presentation = "application/vnd.google-apps.presentation"
    static let form = "application/vnd.google-apps.form"
    static let drawing = "application/vnd.google-apps.drawing"
    static let shortcut = "application/vnd.google-apps.shortcut"

    /// Whether a (non-Google-native) mime type is plausibly UTF-8 text we can
    /// show inline: anything `text/*`, plus the common structured-text types.
    static func isTextual(_ mime: String) -> Bool {
        if mime.hasPrefix("text/") { return true }
        switch mime {
        case "application/json",
             "application/xml",
             "application/javascript",
             "application/x-yaml",
             "application/yaml",
             "application/csv",
             "application/rtf":
            return true
        default:
            return false
        }
    }

    /// An SF Symbol describing a file by its mime type.
    static func symbol(for mime: String?) -> String {
        guard let mime else { return "doc" }
        switch mime {
        case folder: return "folder.fill"
        case document: return "doc.richtext"
        case spreadsheet: return "tablecells"
        case presentation: return "rectangle.on.rectangle"
        case form: return "list.bullet.rectangle"
        case drawing: return "scribble.variable"
        case shortcut: return "arrowshape.turn.up.right"
        default: break
        }
        if mime.hasPrefix("image/") { return "photo" }
        if mime.hasPrefix("video/") { return "film" }
        if mime.hasPrefix("audio/") { return "waveform" }
        if mime.hasPrefix("text/") { return "doc.text" }
        if mime == "application/pdf" { return "doc.text.fill" }
        if mime == "application/zip" || mime.hasSuffix("+zip") { return "archivebox" }
        return "doc"
    }

    /// A short, human label for a mime type (folder, Google Doc, PDF, image, …).
    static func label(for mime: String?) -> String {
        guard let mime else { return "File" }
        switch mime {
        case folder: return "Folder"
        case document: return "Google Doc"
        case spreadsheet: return "Google Sheet"
        case presentation: return "Google Slides"
        case form: return "Google Form"
        case drawing: return "Google Drawing"
        case shortcut: return "Shortcut"
        case "application/pdf": return "PDF"
        default: break
        }
        if mime.hasPrefix("image/") { return "Image" }
        if mime.hasPrefix("video/") { return "Video" }
        if mime.hasPrefix("audio/") { return "Audio" }
        if mime.hasPrefix("text/") { return "Text" }
        return mime
    }
}
