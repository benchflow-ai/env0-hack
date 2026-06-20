import SwiftUI
import Env0Kit

/// The Drive tab's root view: a searchable browser of files and folders served
/// by `drive.listFiles`. Embedded by `RootView` inside a `NavigationStack`, so
/// it sets a title and a `.navigationDestination` but never wraps itself in a
/// stack.
///
/// The `.searchable` text drives the store's Drive `q` (`name contains '…'`) on
/// submit; tapping a row opens its ``FileDetailView`` (routed by file id).
struct DriveListView: View {
    @Environment(AppSettings.self) private var settings
    @State private var store = DriveStore()

    var body: some View {
        @Bindable var store = store
        LoadableView(store.state, retry: { Task { await store.load(settings.suite) } }) { files in
            content(files)
        }
        .navigationTitle("Drive")
        .searchable(text: $store.query, prompt: "Search files")
        .onSubmit(of: .search) {
            Task { await store.load(settings.suite) }
        }
        .navigationDestination(for: String.self) { fileId in
            FileDetailView(fileId: fileId)
        }
        .task { await store.load(settings.suite) }
        .refreshable { await store.load(settings.suite) }
    }

    @ViewBuilder
    private func content(_ files: [DriveFile]) -> some View {
        if files.isEmpty {
            ContentUnavailableView(
                store.query.isEmpty ? "No Files" : "No Results",
                systemImage: "internaldrive",
                description: Text(
                    store.query.isEmpty
                        ? "Your Drive is empty."
                        : "No files match \"\(store.query)\"."
                )
            )
        } else {
            List(files, id: \.id) { file in
                if let id = file.id {
                    NavigationLink(value: id) {
                        DriveFileRow(file: file)
                    }
                }
            }
            .listStyle(.plain)
        }
    }
}

/// One row in the file list: a mime-typed icon, the file name, and a secondary
/// line of owner + relative modified time. Folders read as folders (filled
/// folder glyph, a chevron-y "Folder" subtitle) and sort no differently — the
/// listing is modified-time ordered like the real Drive "Recent" view.
private struct DriveFileRow: View {
    let file: DriveFile

    private var isFolder: Bool { file.mimeType == DriveMime.folder }

    var body: some View {
        HStack(spacing: Theme.Spacing.m) {
            Image(systemName: DriveMime.symbol(for: file.mimeType))
                .font(.title3)
                .foregroundStyle(isFolder ? Theme.drive : Color.secondary)
                .frame(width: 28)

            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                Text(file.name ?? "Untitled")
                    .font(.subheadline)
                    .fontWeight(isFolder ? .semibold : .regular)
                    .lineLimit(1)

                Text(subtitle)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 0)

            if isFolder {
                Image(systemName: "chevron.right")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, Theme.Spacing.xs)
    }

    /// "<owner> · <relative modified>" — each part omitted if unknown. Folders
    /// fall back to the "Folder" type label when there's nothing else to show.
    private var subtitle: String {
        var parts: [String] = []
        if let owner = ownerName {
            parts.append(owner)
        }
        if let modified = file.modifiedTimeDate {
            parts.append(Self.relative.localizedString(for: modified, relativeTo: .now))
        }
        if parts.isEmpty {
            return DriveMime.label(for: file.mimeType)
        }
        return parts.joined(separator: " · ")
    }

    /// The first owner's display name (falling back to its email), if present.
    private var ownerName: String? {
        guard let owner = file.owners?.first else { return nil }
        if let name = owner.displayName, !name.isEmpty { return name }
        return owner.emailAddress
    }

    private static let relative: RelativeDateTimeFormatter = {
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .abbreviated
        return f
    }()
}
