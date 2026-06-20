import SwiftUI
import Env0Kit

/// A single Drive file's detail: full metadata, who has access, and (for
/// text-ish non-Google files) an on-demand text preview. Reached via
/// `.navigationDestination(for: String.self)` from ``DriveListView`` with the
/// file id as the route payload.
///
/// Metadata loads from `drive.getFile`, access from `drive.getFilePermissions`,
/// and the preview from `drive.downloadFileContent` decoded as UTF-8. Folders
/// have no content; Google-native types show an export note instead of a raw
/// download.
struct FileDetailView: View {
    @Environment(AppSettings.self) private var settings

    @State private var store: FileDetailStore

    init(fileId: String) {
        _store = State(initialValue: FileDetailStore(fileId: fileId))
    }

    var body: some View {
        LoadableView(store.metadata, retry: { Task { await store.load(settings.suite) } }) { file in
            content(file)
        }
        .navigationTitle(store.file?.name ?? "File")
        .navigationBarTitleDisplayMode(.inline)
        .task { await store.load(settings.suite) }
    }

    @ViewBuilder
    private func content(_ file: DriveFile) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.l) {
                header(file)
                metadataCard(file)
                accessCard
                contentCard(file)
            }
            .padding(Theme.Spacing.l)
        }
    }

    // MARK: - Header

    @ViewBuilder
    private func header(_ file: DriveFile) -> some View {
        HStack(spacing: Theme.Spacing.m) {
            Image(systemName: DriveMime.symbol(for: file.mimeType))
                .font(.largeTitle)
                .foregroundStyle(Theme.drive)
                .frame(width: 44)

            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                Text(file.name ?? "Untitled")
                    .font(.headline)
                    .lineLimit(2)
                Text(DriveMime.label(for: file.mimeType))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
    }

    // MARK: - Metadata

    @ViewBuilder
    private func metadataCard(_ file: DriveFile) -> some View {
        GlassCard {
            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                sectionTitle("Details")

                metaRow("Type", DriveMime.label(for: file.mimeType))
                metaRow("MIME", file.mimeType ?? "—")
                if let size = formattedSize(file.size) {
                    metaRow("Size", size)
                }
                metaRow("Owners", ownersText(file) ?? "—")
                if let modified = file.modifiedTimeDate {
                    metaRow("Modified", Self.absolute.string(from: modified))
                }
                if let created = file.createdTimeDate {
                    metaRow("Created", Self.absolute.string(from: created))
                }
                if file.shared == true {
                    Label("Shared", systemImage: "person.2.fill")
                        .font(.caption)
                        .foregroundStyle(Theme.drive)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: - Access (permissions)

    @ViewBuilder
    private var accessCard: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                sectionTitle("Who has access")

                switch store.permissions {
                case .idle, .loading:
                    ProgressView()
                        .frame(maxWidth: .infinity, alignment: .center)
                case .failed(let message):
                    Label(message, systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                case .loaded(let perms):
                    if perms.isEmpty {
                        Text("No one else has access.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(Array(perms.enumerated()), id: \.offset) { _, perm in
                            PermissionRow(permission: perm)
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: - Content / preview

    @ViewBuilder
    private func contentCard(_ file: DriveFile) -> some View {
        GlassCard {
            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                sectionTitle("Content")

                if store.isFolder {
                    Label("This is a folder — it has no content to preview.",
                          systemImage: "folder")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else if store.isGoogleNative {
                    VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                        Label("Google-native file", systemImage: "doc.richtext")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text("This \(DriveMime.label(for: file.mimeType)) can't be downloaded directly; it must be exported (e.g. to text) to read its contents.")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                } else if store.canPreview {
                    previewSection
                } else {
                    Label("No inline preview is available for this file type.",
                          systemImage: "eye.slash")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private var previewSection: some View {
        switch store.preview {
        case .idle:
            Button {
                Task { await store.loadPreview(settings.suite) }
            } label: {
                Label("Preview", systemImage: "eye")
            }
            .buttonStyle(.glassProminent)
            .tint(Theme.drive)
        case .loading:
            ProgressView()
                .frame(maxWidth: .infinity, alignment: .center)
        case .failed(let message):
            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                Label(message, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button("Try Again") {
                    Task { await store.loadPreview(settings.suite) }
                }
                .buttonStyle(.glass)
            }
        case .loaded(let text):
            Text(text.isEmpty ? "(empty file)" : text)
                .font(.system(.footnote, design: .monospaced))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: - Building blocks

    @ViewBuilder
    private func sectionTitle(_ title: String) -> some View {
        Text(title)
            .font(.subheadline)
            .fontWeight(.semibold)
            .foregroundStyle(Theme.drive)
    }

    @ViewBuilder
    private func metaRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(width: 80, alignment: .leading)
            Text(value)
                .font(.caption)
                .foregroundStyle(.primary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        }
    }

    // MARK: - Formatting

    /// All owner names (falling back to email), comma-joined.
    private func ownersText(_ file: DriveFile) -> String? {
        let names = (file.owners ?? []).compactMap { owner -> String? in
            if let name = owner.displayName, !name.isEmpty { return name }
            return owner.emailAddress
        }
        return names.isEmpty ? nil : names.joined(separator: ", ")
    }

    /// Format Drive's int64-as-string `size` into a human byte count.
    private func formattedSize(_ raw: String?) -> String? {
        guard let raw, let bytes = Int64(raw) else { return nil }
        return ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file)
    }

    private static let absolute: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .short
        return f
    }()
}

/// One access entry: a type/role icon, the grantee (name/email/domain/"Anyone")
/// and the role they hold (owner, writer, reader, …).
private struct PermissionRow: View {
    let permission: DrivePermission

    var body: some View {
        HStack(spacing: Theme.Spacing.m) {
            Image(systemName: symbol)
                .font(.body)
                .foregroundStyle(Theme.drive)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 1) {
                Text(grantee)
                    .font(.caption)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                Text(roleLabel)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, Theme.Spacing.xs)
    }

    /// Who the permission is granted to.
    private var grantee: String {
        if let name = permission.displayName, !name.isEmpty { return name }
        if let email = permission.emailAddress, !email.isEmpty { return email }
        switch permission.type {
        case .anyone: return "Anyone with the link"
        case .domain: return permission.domain.map { "Everyone at \($0)" } ?? "Domain"
        default: return "Unknown"
        }
    }

    /// Human role label (capitalized raw value), e.g. "Owner", "Writer".
    private var roleLabel: String {
        let role = permission.role ?? .unknown
        switch role {
        case .owner: return "Owner"
        case .organizer: return "Organizer"
        case .fileOrganizer: return "File organizer"
        case .writer: return "Editor"
        case .commenter: return "Commenter"
        case .reader: return "Viewer"
        case .unknown: return "Access"
        }
    }

    /// An icon keyed on the grantee type.
    private var symbol: String {
        switch permission.type {
        case .user: return "person.crop.circle"
        case .group: return "person.2.circle"
        case .domain: return "building.2"
        case .anyone: return "globe"
        case .unknown, .none: return "person.crop.circle.badge.questionmark"
        }
    }
}
