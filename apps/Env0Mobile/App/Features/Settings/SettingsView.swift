import SwiftUI
import Env0Kit

/// Configure the env-0 host and check that the four services are reachable.
struct SettingsView: View {
    @Environment(AppSettings.self) private var settings
    @State private var draftHost = ""

    var body: some View {
        Form {
            Section {
                TextField("host or IP", text: $draftHost)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .onSubmit(apply)
                Button {
                    apply()
                    Task { await settings.refreshHealth() }
                } label: {
                    HStack {
                        Text("Apply & Test Connection")
                        Spacer()
                        if settings.isCheckingHealth { ProgressView() }
                    }
                }
            } header: {
                Text("env-0 host")
            } footer: {
                Text("Standard ports are derived automatically: Gmail 9001, Calendar 9003, Docs 9004, Drive 9005. From the iOS Simulator use 127.0.0.1; from a device use your dev machine's LAN IP.")
            }

            Section("Services") {
                healthRow("Gmail", systemImage: "envelope.fill", tint: Theme.mail,
                          url: settings.environment.gmail, ok: settings.health?.gmail)
                healthRow("Calendar", systemImage: "calendar", tint: Theme.calendar,
                          url: settings.environment.calendar, ok: settings.health?.calendar)
                healthRow("Docs", systemImage: "doc.text.fill", tint: Theme.docs,
                          url: settings.environment.docs, ok: settings.health?.docs)
                healthRow("Drive", systemImage: "internaldrive.fill", tint: Theme.drive,
                          url: settings.environment.drive, ok: settings.health?.drive)
            }

            Section {
                LabeledContent("About", value: "Env0 Mobile")
                Text("A mobile client for the env-0 mock Google Workspace suite. It speaks the real Google REST wire format, so it points at a local env-0 deployment instead of googleapis.com.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Settings")
        .task {
            draftHost = settings.host
            if settings.health == nil { await settings.refreshHealth() }
        }
    }

    private func apply() {
        let trimmed = draftHost.trimmingCharacters(in: .whitespaces)
        if !trimmed.isEmpty { settings.host = trimmed }
    }

    @ViewBuilder
    private func healthRow(_ name: String, systemImage: String, tint: Color, url: URL, ok: Bool?) -> some View {
        HStack {
            Label(name, systemImage: systemImage)
                .foregroundStyle(tint)
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                statusBadge(ok)
                Text(url.absoluteString)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
    }

    @ViewBuilder
    private func statusBadge(_ ok: Bool?) -> some View {
        switch ok {
        case .some(true):
            Label("Online", systemImage: "checkmark.circle.fill")
                .labelStyle(.titleAndIcon).font(.caption).foregroundStyle(.green)
        case .some(false):
            Label("Offline", systemImage: "xmark.circle.fill")
                .labelStyle(.titleAndIcon).font(.caption).foregroundStyle(.red)
        case .none:
            Text("Unknown").font(.caption).foregroundStyle(.secondary)
        }
    }
}
