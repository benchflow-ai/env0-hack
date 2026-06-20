import SwiftUI

/// The five-tab shell. Each tab owns its own `NavigationStack` (per house
/// style). The tab bar renders as Liquid Glass automatically on the iOS 26 SDK.
struct RootView: View {
    @State private var selection: AppTab = .mail

    var body: some View {
        TabView(selection: $selection) {
            Tab("Mail", systemImage: "envelope.fill", value: AppTab.mail) {
                NavigationStack { MailListView() }
            }
            Tab("Calendar", systemImage: "calendar", value: AppTab.calendar) {
                NavigationStack { CalendarView() }
            }
            Tab("Docs", systemImage: "doc.text.fill", value: AppTab.docs) {
                NavigationStack { DocsListView() }
            }
            Tab("Drive", systemImage: "internaldrive.fill", value: AppTab.drive) {
                NavigationStack { DriveListView() }
            }
            Tab("Settings", systemImage: "gearshape.fill", value: AppTab.settings) {
                NavigationStack { SettingsView() }
            }
        }
        .tint(selection.accent)
    }
}

enum AppTab: Hashable {
    case mail, calendar, docs, drive, settings

    var accent: Color {
        switch self {
        case .mail: Theme.mail
        case .calendar: Theme.calendar
        case .docs: Theme.docs
        case .drive: Theme.drive
        case .settings: .secondary
        }
    }
}
