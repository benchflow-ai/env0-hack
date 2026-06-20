import SwiftUI

/// Composition root. Builds the single ``AppSettings`` (which owns the live
/// ``Env0Suite``), injects it into the environment, and probes service health
/// on launch. Every feature reads `AppSettings` from the environment.
@main
struct Env0MobileApp: App {
    @State private var settings = AppSettings()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(settings)
                .task { await settings.refreshHealth() }
        }
    }
}
