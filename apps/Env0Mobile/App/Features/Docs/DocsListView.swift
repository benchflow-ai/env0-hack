import SwiftUI
import Env0Kit

/// A lightweight route payload for programmatically pushing a just-created doc.
/// It's `Identifiable & Hashable` so it can drive `.navigationDestination(item:)`
/// as a *distinct* value type from the row route (a bare `String`), avoiding a
/// duplicate `String` destination registration on the same stack.
private struct NewDocRoute: Identifiable, Hashable {
    let documentId: String
    var id: String { documentId }
}

/// The Docs tab's root view: a list of the user's Google Docs. Embedded by
/// `RootView` inside a `NavigationStack`, so it sets a title and a
/// `.navigationDestination` but never wraps itself in a stack.
///
/// Google Docs has no list endpoint, so the list is sourced from Drive
/// (`drive.listFiles` filtered to the Google-Docs mimeType) — the real-world
/// pattern. Each row shows the file's name and last-modified time; tapping opens
/// the document through the Docs service in `DocDetailView`. The toolbar "+"
/// creates a new doc via `docs.createDocument(title:)` and navigates into it.
struct DocsListView: View {
    @Environment(AppSettings.self) private var settings
    @State private var store = DocsStore()

    /// A freshly-created document to push once its id comes back from the create
    /// call. Bound to `.navigationDestination(item:)` for the programmatic push;
    /// the surrounding `NavigationStack` (owned by `RootView`) handles the rest.
    /// It's a distinct type from the row route (`String`) so the two
    /// `.navigationDestination`s don't register the same value type twice.
    @State private var newlyCreatedDoc: NewDocRoute?

    /// Drives the "New Document" title prompt.
    @State private var isNamingDoc = false
    @State private var newDocTitle = ""

    init() {}

    var body: some View {
        LoadableView(store.state, retry: { Task { await store.load(settings.suite) } }) { docs in
            content(docs)
        }
        .navigationTitle("Docs")
        // Tapping an existing row pushes by id.
        .navigationDestination(for: String.self) { documentId in
            DocDetailView(documentId: documentId)
        }
        // Programmatic push of a just-created doc (distinct route type).
        .navigationDestination(item: $newlyCreatedDoc) { route in
            DocDetailView(documentId: route.documentId)
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    newDocTitle = ""
                    isNamingDoc = true
                } label: {
                    Label("New Document", systemImage: "plus")
                }
                .disabled(store.isCreating)
            }
        }
        .overlay {
            if store.isCreating {
                ProgressView("Creating…").controlSize(.large)
            }
        }
        .alert("New Document", isPresented: $isNamingDoc) {
            TextField("Title", text: $newDocTitle)
            Button("Cancel", role: .cancel) {}
            Button("Create") {
                Task { await create() }
            }
        } message: {
            Text("Name your new document.")
        }
        .alert(
            "Couldn't Create Document",
            isPresented: Binding(
                get: { store.createError != nil },
                set: { if !$0 { store.createError = nil } }
            ),
            presenting: store.createError
        ) { _ in
            Button("OK", role: .cancel) {}
        } message: { message in
            Text(message)
        }
        .task { await store.load(settings.suite) }
        .refreshable { await store.load(settings.suite) }
    }

    /// Create a doc, then push into it via the bound destination item.
    private func create() async {
        if let id = await store.createDocument(settings.suite, title: newDocTitle) {
            newlyCreatedDoc = NewDocRoute(documentId: id)
        }
    }

    @ViewBuilder
    private func content(_ docs: [DriveFile]) -> some View {
        if docs.isEmpty {
            ContentUnavailableView(
                "No Documents",
                systemImage: "doc.text",
                description: Text("Tap + to create your first document.")
            )
        } else {
            List(docs, id: \.id) { doc in
                NavigationLink(value: doc.id ?? "") {
                    DocRow(file: doc)
                }
            }
            .listStyle(.plain)
        }
    }
}

/// One row in the docs list: the document's name and a relative "modified" date,
/// sourced from the Drive ``DriveFile`` projection.
private struct DocRow: View {
    let file: DriveFile

    private var displayName: String {
        let name = file.name?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return name.isEmpty ? "Untitled document" : name
    }

    var body: some View {
        HStack(spacing: Theme.Spacing.m) {
            Image(systemName: "doc.text.fill")
                .font(.title3)
                .foregroundStyle(Theme.docs)

            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                Text(displayName)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.primary)
                    .lineLimit(1)

                if let modified = file.modifiedTimeDate {
                    Text("Modified \(modified, format: .relative(presentation: .named))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
        }
        .padding(.vertical, Theme.Spacing.xs)
    }
}
