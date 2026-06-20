import SwiftUI
import Env0Kit

/// A lightweight, `Identifiable` payload describing a compose session — either a
/// fresh message or a reply within an existing thread. Used as the `.sheet(item:)`
/// route so it carries the prefilled fields without passing a view instance.
struct ComposeRoute: Identifiable, Hashable {
    let id = UUID()
    var to: String = ""
    var subject: String = ""
    var body: String = ""
    /// Set when replying within an existing thread.
    var threadId: String?
}

/// Compose or reply to a message, presented as a `.sheet`. Builds a
/// `GmailCompose` and either sends it (the primary action) or saves it as a
/// draft. Defaulting the prominent action to Send is the safe, explicit choice;
/// "Save as Draft" is offered as a clearly-labelled secondary action.
struct ComposeView: View {
    @Environment(AppSettings.self) private var settings
    @Environment(\.dismiss) private var dismiss

    @State private var route: ComposeRoute
    @State private var isWorking = false
    @State private var errorMessage: String?

    /// New, empty message (the compose `+` action).
    init() {
        _route = State(initialValue: ComposeRoute())
    }

    /// Compose seeded from a route — e.g. a reply carrying the recipient,
    /// subject and originating thread id.
    init(route: ComposeRoute) {
        _route = State(initialValue: route)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("To", text: $route.to)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.emailAddress)
                    TextField("Subject", text: $route.subject)
                }
                Section("Message") {
                    TextField("Body", text: $route.body, axis: .vertical)
                        .lineLimit(6...20)
                }
                if route.threadId != nil {
                    Section {
                        Label("Replying within this thread", systemImage: "arrowshape.turn.up.left")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle(route.threadId == nil ? "New Message" : "Reply")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { toolbarContent }
            .disabled(isWorking)
            .overlay {
                if isWorking {
                    ProgressView().controlSize(.large)
                }
            }
            .alert(
                "Couldn't Complete",
                isPresented: Binding(
                    get: { errorMessage != nil },
                    set: { if !$0 { errorMessage = nil } }
                ),
                presenting: errorMessage
            ) { _ in
                Button("OK", role: .cancel) {}
            } message: { message in
                Text(message)
            }
        }
        .presentationSizing(.form)
    }

    // MARK: - Toolbar

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .cancellationAction) {
            Button("Cancel", role: .cancel) { dismiss() }
        }
        ToolbarItem(placement: .secondaryAction) {
            Button {
                Task { await saveDraft() }
            } label: {
                Label("Save as Draft", systemImage: "tray.and.arrow.down")
            }
            .disabled(!canSubmit)
        }
        // Primary action defaults to Send — explicit and prominent.
        ToolbarItem(placement: .confirmationAction) {
            Button {
                Task { await send() }
            } label: {
                Label("Send", systemImage: "paperplane.fill")
            }
            .buttonStyle(.glassProminent)
            .tint(Theme.mail)
            .disabled(!canSubmit)
        }
    }

    // MARK: - Validation

    /// Require at least a recipient before either action is allowed.
    private var canSubmit: Bool {
        !route.to.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var compose: GmailCompose {
        GmailCompose(
            to: route.to.trimmingCharacters(in: .whitespacesAndNewlines),
            subject: route.subject,
            body: route.body
        )
    }

    // MARK: - Actions

    private func send() async {
        await perform {
            try await settings.suite.gmail.send(compose, threadId: route.threadId)
        }
    }

    private func saveDraft() async {
        await perform {
            _ = try await settings.suite.gmail.draft(compose, threadId: route.threadId)
        }
    }

    private func perform(_ action: () async throws -> Void) async {
        isWorking = true
        defer { isWorking = false }
        do {
            try await action()
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
