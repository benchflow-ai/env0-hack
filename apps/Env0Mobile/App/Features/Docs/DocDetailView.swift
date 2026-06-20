import SwiftUI
import Env0Kit

/// Detail screen for one Google Doc, reached via
/// `.navigationDestination(for: String.self)` (the route payload is the document
/// id) or pushed programmatically after a create.
///
/// Reads the document with `docs.getDocument(documentId:)` and renders its
/// ``GDocDocument/title`` and flattened ``GDocDocument/plainText`` in a
/// scrollable, readable text view. An "Edit" toggle swaps the reader for a
/// `TextEditor`; "Save" writes the whole body back via
/// `docs.saveDocument(documentId:content:)` and reloads so the rendered text
/// reflects the server's re-paragraphing.
struct DocDetailView: View {
    @Environment(AppSettings.self) private var settings

    let documentId: String

    @State private var store: DocDetailStore

    /// Whether the editor is showing instead of the reader.
    @State private var isEditing = false

    /// The working copy bound to the `TextEditor` while editing.
    @State private var draft = ""

    init(documentId: String) {
        self.documentId = documentId
        _store = State(initialValue: DocDetailStore(documentId: documentId))
    }

    var body: some View {
        LoadableView(
            store.state,
            retry: { Task { await store.load(settings.suite) } }
        ) { document in
            content(document)
        }
        .navigationTitle(store.state.value?.title ?? "Document")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { toolbarContent }
        .overlay {
            if store.isSaving {
                ProgressView("Saving…").controlSize(.large)
            }
        }
        .alert(
            "Couldn't Save",
            isPresented: Binding(
                get: { store.saveError != nil },
                set: { if !$0 { store.saveError = nil } }
            ),
            presenting: store.saveError
        ) { _ in
            Button("OK", role: .cancel) {}
        } message: { message in
            Text(message)
        }
        .task { await store.load(settings.suite) }
    }

    // MARK: - Content

    @ViewBuilder
    private func content(_ document: GDocDocument) -> some View {
        if isEditing {
            editor
        } else {
            reader(document)
        }
    }

    /// Read mode: title + flattened plain text in a readable, scrollable column.
    @ViewBuilder
    private func reader(_ document: GDocDocument) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.l) {
                Text(document.title.isEmpty ? "Untitled document" : document.title)
                    .font(.title.bold())
                    .frame(maxWidth: .infinity, alignment: .leading)

                let text = document.plainText.trimmingCharacters(in: .whitespacesAndNewlines)
                if text.isEmpty {
                    Text("This document is empty. Tap Edit to start writing.")
                        .font(.body)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    Text(document.plainText)
                        .font(.body)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(Theme.Spacing.l)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// Edit mode: a full-height `TextEditor` over the document's plain text on a
    /// glass surface.
    @ViewBuilder
    private var editor: some View {
        TextEditor(text: $draft)
            .font(.body)
            .scrollContentBackground(.hidden)
            .padding(Theme.Spacing.m)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .glassEffect(.regular, in: .rect(cornerRadius: 16))
            .padding(Theme.Spacing.l)
            .disabled(store.isSaving)
    }

    // MARK: - Toolbar

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        if isEditing {
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel", role: .cancel) {
                    isEditing = false
                }
                .disabled(store.isSaving)
            }
            ToolbarItem(placement: .confirmationAction) {
                Button {
                    Task { await save() }
                } label: {
                    Label("Save", systemImage: "checkmark")
                }
                .buttonStyle(.glassProminent)
                .tint(Theme.docs)
                .disabled(store.isSaving)
            }
        } else {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    beginEditing()
                } label: {
                    Label("Edit", systemImage: "pencil")
                }
                // Can only edit once the document has loaded.
                .disabled(store.state.value == nil)
            }
        }
    }

    // MARK: - Actions

    /// Seed the draft from the current body and enter edit mode.
    private func beginEditing() {
        draft = store.state.value?.plainText ?? ""
        isEditing = true
    }

    /// Persist the draft, then drop back to read mode on success.
    private func save() async {
        if await store.save(settings.suite, content: draft) {
            isEditing = false
        }
    }
}
