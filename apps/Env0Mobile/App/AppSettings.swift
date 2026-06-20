import Foundation
import Observation
import Env0Kit

/// App-wide configuration + the live ``Env0Suite``. This is the composition
/// root's single source of truth: the user edits the host in Settings, and
/// every feature reads `settings.suite`.
///
/// `@MainActor @Observable` per house style — it drives UI. The host is
/// persisted in `UserDefaults` (with a `didSet`, since `@AppStorage` is invisible
/// to `@Observable`).
@MainActor
@Observable
public final class AppSettings {
    /// Host of the env-0 deployment (no scheme/port). Per-service ports are
    /// derived via ``Env0Environment/localPorts(host:scheme:)``.
    public var host: String {
        didSet { UserDefaults.standard.set(host, forKey: Keys.host) }
    }

    /// Last known liveness of the four services; `nil` until first probed.
    public private(set) var health: ServiceHealth?
    public private(set) var isCheckingHealth = false

    /// The configured environment + suite, rebuilt whenever `host` changes.
    public var environment: Env0Environment { .localPorts(host: host) }
    public var suite: Env0Suite { Env0Suite(environment: environment) }

    private enum Keys { static let host = "env0.host" }

    public init() {
        self.host = UserDefaults.standard.string(forKey: Keys.host) ?? "127.0.0.1"
    }

    /// Probe all four `/health` endpoints and store the result.
    public func refreshHealth() async {
        isCheckingHealth = true
        defer { isCheckingHealth = false }
        health = await suite.health()
    }
}
