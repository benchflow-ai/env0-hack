import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// The whole env-0 Google Workspace surface behind one value: a configured
/// client per service, all sharing a single `URLSession`. This is what the app
/// composition root builds from an ``Env0Environment`` and hands down to the UI.
public struct Env0Suite: Sendable {
    public let environment: Env0Environment
    public let gmail: GmailService
    public let calendar: CalendarService
    public let docs: DocsService
    public let drive: DriveService

    private let gmailClient: Env0APIClient
    private let calendarClient: Env0APIClient
    private let docsClient: Env0APIClient
    private let driveClient: Env0APIClient

    public init(
        environment: Env0Environment,
        session: URLSession = Env0APIClient.makeSession()
    ) {
        self.environment = environment
        self.gmailClient = Env0APIClient(baseURL: environment.gmail, session: session)
        self.calendarClient = Env0APIClient(baseURL: environment.calendar, session: session)
        self.docsClient = Env0APIClient(baseURL: environment.docs, session: session)
        self.driveClient = Env0APIClient(baseURL: environment.drive, session: session)
        self.gmail = GmailService(client: gmailClient)
        self.calendar = CalendarService(client: calendarClient)
        self.docs = DocsService(client: docsClient)
        self.drive = DriveService(client: driveClient)
    }

    /// Liveness of each service's `/health` endpoint (root path, no API prefix).
    /// Used by Settings to confirm the configured host is reachable before the
    /// user dives into a tab.
    public func health() async -> ServiceHealth {
        async let gmailOK = Self.ping(gmailClient)
        async let calendarOK = Self.ping(calendarClient)
        async let docsOK = Self.ping(docsClient)
        async let driveOK = Self.ping(driveClient)
        return await ServiceHealth(
            gmail: gmailOK,
            calendar: calendarOK,
            docs: docsOK,
            drive: driveOK
        )
    }

    private static func ping(_ client: Env0APIClient) async -> Bool {
        guard let health = try? await client.get(HealthResponse.self, Endpoint("/health")) else {
            return false
        }
        return health.status.lowercased() == "ok"
    }
}

/// Per-service liveness snapshot.
public struct ServiceHealth: Sendable, Equatable {
    public let gmail: Bool
    public let calendar: Bool
    public let docs: Bool
    public let drive: Bool

    public var allHealthy: Bool { gmail && calendar && docs && drive }
    public var anyHealthy: Bool { gmail || calendar || docs || drive }
}

struct HealthResponse: Decodable, Sendable {
    let status: String
}
