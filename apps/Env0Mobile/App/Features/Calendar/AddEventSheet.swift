import SwiftUI
import Env0Kit

/// A lightweight "add event" sheet. Collects a title, optional location, and a
/// timed start/end, builds an `EventWriteRequest`, and calls
/// `calendar.createEvent` on the store's primary calendar. Optional / nice-to-have.
struct AddEventSheet: View {
    @Environment(AppSettings.self) private var settings
    @Environment(\.dismiss) private var dismiss
    let store: CalendarStore

    @State private var summary = ""
    @State private var location = ""
    @State private var start = Date()
    @State private var end = Date().addingTimeInterval(3600)
    @State private var isSaving = false
    @State private var errorMessage: String?

    private var canSave: Bool {
        !summary.trimmingCharacters(in: .whitespaces).isEmpty && end > start && !isSaving
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Details") {
                    TextField("Title", text: $summary)
                    TextField("Location", text: $location)
                }
                Section("When") {
                    DatePicker("Starts", selection: $start)
                    DatePicker("Ends", selection: $end, in: start...)
                }
                if let errorMessage {
                    Section {
                        Label(errorMessage, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                            .font(.footnote)
                    }
                }
            }
            .navigationTitle("New Event")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add", action: save)
                        .disabled(!canSave)
                }
            }
            .presentationSizing(.form)
            .interactiveDismissDisabled(isSaving)
        }
    }

    private func save() {
        isSaving = true
        errorMessage = nil
        Task {
            defer { isSaving = false }
            do {
                try await store.createEvent(
                    settings.suite,
                    summary: summary.trimmingCharacters(in: .whitespaces),
                    location: location.trimmingCharacters(in: .whitespaces),
                    start: start,
                    end: end
                )
                dismiss()
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }
}
