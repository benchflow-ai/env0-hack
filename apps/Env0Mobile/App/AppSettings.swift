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
        didSet {
            UserDefaults.standard.set(host, forKey: Keys.host)
            // Rebuild the suite (and its long-lived URLSession) only when the
            // host actually changes — not on every read.
            suite = Env0Suite(environment: environment)
        }
    }

    /// The live suite. Stored (not computed) so its `URLSession` and four
    /// service clients are reused across view-body re-evaluations; rebuilt only
    /// in `init` and `host`'s `didSet`.
    public private(set) var suite: Env0Suite

    /// Last known liveness of the four services; `nil` until first probed.
    public private(set) var health: ServiceHealth?
    public private(set) var isCheckingHealth = false

    /// The configured environment (cheap + Equatable, so it stays computed).
    public var environment: Env0Environment { .localPorts(host: host) }

    private enum Keys { static let host = "env0.host" }

    public init() {
        let host = UserDefaults.standard.string(forKey: Keys.host) ?? "127.0.0.1"
        self.host = host
        self.suite = Env0Suite(environment: .localPorts(host: host))
    }

    /// Probe all four `/health` endpoints and store the result.
    public func refreshHealth() async {
        isCheckingHealth = true
        defer { isCheckingHealth = false }
        health = await suite.health()
    }
}
