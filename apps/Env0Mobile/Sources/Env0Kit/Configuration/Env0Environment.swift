import Foundation

/// Where the four mock services live. The env-0 suite mirrors the real Google
/// REST wire format, so the only thing that changes versus production is the
/// base URL — point these at a running env-0 instance and the typed services
/// work unchanged.
///
/// Ports come from the repo's `config.toml` (single source of truth):
/// gmail 9001, gcal/calendar 9003, gdoc/docs 9004, gdrive/drive 9005,
/// auth 9000. A dev "gateway" can also serve every service from one port via
/// Host-subdomain routing (see ``gateway(host:port:scheme:)``).
public struct Env0Environment: Sendable, Equatable {
    public var gmail: URL
    public var calendar: URL
    public var docs: URL
    public var drive: URL
    public var auth: URL?

    public init(gmail: URL, calendar: URL, docs: URL, drive: URL, auth: URL? = nil) {
        self.gmail = gmail
        self.calendar = calendar
        self.docs = docs
        self.drive = drive
        self.auth = auth
    }

    /// Direct per-service ports, e.g. `http://127.0.0.1:9001`. Use this when the
    /// services are started individually (`scripts/launch.sh`) or via the
    /// per-service Docker images. From the iOS Simulator, `127.0.0.1` reaches
    /// the host Mac; from a physical device use the Mac's LAN IP.
    public static func localPorts(
        host: String = "127.0.0.1",
        scheme: String = "http"
    ) -> Env0Environment {
        func url(_ port: Int) -> URL {
            URL(string: "\(scheme)://\(host):\(port)")!
        }
        return Env0Environment(
            gmail: url(9001),
            calendar: url(9003),
            docs: url(9004),
            drive: url(9005),
            auth: url(9000)
        )
    }

    /// The dev gateway that serves every service from one port via subdomain
    /// routing (`gmail.localhost:8080`, `gcal.localhost:8080`, …).
    public static func gateway(
        host: String = "localhost",
        port: Int = 8080,
        scheme: String = "http"
    ) -> Env0Environment {
        func url(_ sub: String) -> URL {
            URL(string: "\(scheme)://\(sub).\(host):\(port)")!
        }
        return Env0Environment(
            gmail: url("gmail"),
            calendar: url("gcal"),
            docs: url("gdoc"),
            drive: url("gdrive"),
            auth: url("auth")
        )
    }

    /// Build from a single base URL by appending per-service ports — handy when
    /// the user types one host in Settings. Assumes the standard port layout.
    public static func host(_ host: String, scheme: String = "http") -> Env0Environment {
        localPorts(host: host, scheme: scheme)
    }
}
