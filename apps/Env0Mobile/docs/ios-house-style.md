I have everything I need. Here is the house style doc.

```markdown
# iOS House Style

Conventions for our **SwiftUI iOS 26 app** + a **platform-agnostic Swift package** (`Networking` + `Models`, builds & tests on Linux with Foundation only). Targets Swift 6.3, strict concurrency. Copy-paste these patterns; deviate only with a comment explaining why.

> Package boundary: the `Core` package (networking + models) imports **Foundation only** — no SwiftUI/UIKit, no `@MainActor` defaults, no `print`. The app target imports `Core` and owns all UI.

---

## 1. Networking layer

One protocol-fronted, injectable async client per package. Inject a configured `URLSession` — never call `URLSession.shared` in production code.

```swift
// MARK: Error type
public enum NetworkError: Error, Sendable {
    case invalidResponse
    case httpError(statusCode: Int, data: Data)
    case decodingFailed(Error)
    case noConnection, timedOut, cancelled

    static func from(_ e: URLError) -> NetworkError {
        switch e.code {
        case .notConnectedToInternet, .networkConnectionLost: .noConnection
        case .timedOut: .timedOut
        case .cancelled: .cancelled
        default: .httpError(statusCode: -1, data: Data())
        }
    }
}

// MARK: Protocol (testable seam — swap implementations, don't mock URLSession)
public protocol APIClientProtocol: Sendable {
    func fetch<T: Decodable & Sendable>(_ type: T.Type, _ endpoint: Endpoint) async throws -> T
}

public struct Endpoint: Sendable {
    public var path: String
    public var method: String = "GET"
    public var queryItems: [URLQueryItem] = []
    public var headers: [String: String] = [:]
    public var body: Data?
}

// MARK: Implementation
public actor APIClient: APIClientProtocol {
    private let baseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder
    private let middleware: [any RequestMiddleware]

    public init(baseURL: URL,
                session: URLSession = .shared,   // inject configured session in production
                decoder: JSONDecoder = .api,
                middleware: [any RequestMiddleware] = []) {
        self.baseURL = baseURL; self.session = session
        self.decoder = decoder; self.middleware = middleware
    }

    public func fetch<T: Decodable & Sendable>(_ type: T.Type, _ endpoint: Endpoint) async throws -> T {
        var request = try buildRequest(endpoint)            // builds URL via URLComponents
        for m in middleware { request = try await m.prepare(request) }
        let (data, response): (Data, URLResponse)
        do { (data, response) = try await session.data(for: request) }
        catch let e as URLError { throw NetworkError.from(e) }

        guard let http = response as? HTTPURLResponse else { throw NetworkError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            throw NetworkError.httpError(statusCode: http.statusCode, data: data)   // validate BEFORE decoding
        }
        do { return try decoder.decode(T.self, from: data) }
        catch { throw NetworkError.decodingFailed(error) }
    }
}

public protocol RequestMiddleware: Sendable {
    func prepare(_ request: URLRequest) async throws -> URLRequest
}
```

Rules:
- **Validate the HTTP status code before decoding.** URLSession only throws on transport failures, never on 4xx/5xx.
- **Auth via middleware**, never hardcoded headers. Tokens live in Keychain, not `UserDefaults`. Handle 401 by refreshing once and retrying.
- **Configure the session** for production (do this in the composition root): `timeoutIntervalForRequest = 30`, `timeoutIntervalForResource = 300`, `waitsForConnectivity = true`, a `URLCache`.
- **Retries:** exponential backoff; skip retry on `CancellationError` and 4xx (except 429). Check `Task.isCancelled` between attempts/pages.
- **Downloads** use `download(for:)` (streams to disk), not `data(for:)`.
- For MV-style features, a closure-struct client (`struct FooClient { var fetch: (…) async throws -> … }` with `.live` / `.mock` factories) is an acceptable lighter alternative to the protocol+actor.

---

## 2. Codable conventions (mirroring Google REST JSON)

- **`Decodable`-only** for read paths; add `Encodable` only where you actually write. All wire models are `Sendable` value types.
- **snake_case → camelCase:** rely on `keyDecodingStrategy = .convertFromSnakeCase` for *mechanical* mappings only.
- **Acronyms break the strategy.** `convertFromSnakeCase` maps by spelling: `image_url → imageUrl`, not `imageURL`. If the Swift property is `imageURL`, `nextPageToken`→`nextPageToken` is fine but `selfLink`/`userID`/`baseURI` need **explicit `CodingKeys`**. Default house spelling is `imageURL`/`userID`, so expect to declare `CodingKeys` for those.
- **Optionals & defaults:** stored-property defaults do *not* make synthesized `Decodable` tolerate a missing required key. Use `decodeIfPresent(...) ?? default` in a custom `init(from:)` when a key may be absent/null.
- **Dates:** Google uses RFC3339/ISO8601 → `decoder.dateDecodingStrategy = .iso8601`. For formats `.iso8601` rejects (fractional seconds in some payloads), use a `.custom` closure trying `ISO8601DateFormatter` with/without `.withFractionalSeconds`.
- **Enums with unknown-case fallback** — required for forward-compatible Google enums:

```swift
enum EventStatus: String, Decodable, Sendable {
    case confirmed, tentative, cancelled
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = EventStatus(rawValue: raw) ?? .unknown   // never throw on a new server value
    }
}
```

- **Envelopes & pagination:** model the Google list shape generically — `struct ListResponse<T: Decodable & Sendable>: Decodable, Sendable { let items: [T]?; let nextPageToken: String? }`. Treat `items` as optional → `?? []`.
- **Shared decoder:** define one `JSONDecoder.api` (and `JSONEncoder.api`) static so config is set once, not per-call.

```swift
extension JSONDecoder {
    static var api: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        d.dateDecodingStrategy = .iso8601
        return d
    }
}
```

- Encoders in tests: include `.sortedKeys` in `outputFormatting` for deterministic output.

---

## 3. Concurrency

- **`@MainActor` goes on UI-touching code only**: SwiftUI views, `@Observable` view models/stores, and `@Observable` routers. Never on the networking/model package.
- **The client is an `actor`** (or a `Sendable` struct of closures). It runs off-main; decoding happens off-main by default. Only hop to `@MainActor` to assign UI state.
- **Models are `Sendable` value types.** Structs/enums are auto-`Sendable` when their stored properties are. Don't add redundant `Sendable` to `@MainActor` classes or actors (already implicit).
- **App target:** enable *Default Actor Isolation = MainActor* + *Approachable Concurrency*. **Package target:** leave actor-agnostic (no default isolation) so it stays reusable and Linux-clean.
- Use `@concurrent` to push heavy work (large decodes, image processing) off the caller's actor. Never block `@MainActor`.
- Use `.task` / `.task(id:)` in views for cancellable async work. **No GCD** (`DispatchQueue`/`DispatchSemaphore`/`DispatchGroup`) anywhere. No locks inside actors; no lock held across `await`.
- Watch actor reentrancy: don't assume actor state is unchanged across an `await`.

---

## 4. App architecture

**Default to MV (Model–View with `@Observable`).** Introduce a view model only when business logic outgrows the view (transformation, multi-view sharing, testability). One pattern per feature module.

```swift
@MainActor
@Observable
final class TripStore {
    private(set) var trips: [Trip] = []
    var isLoading = false
    var error: Error?

    private let client: any APIClientProtocol   // injected, private

    init(client: any APIClientProtocol) { self.client = client }

    func load() async {
        isLoading = true; defer { isLoading = false }
        do { trips = try await client.fetch([Trip].self, .trips) }
        catch { self.error = error }
    }
}
```

DI rules:
- **Inject services, never construct them inside a model/view.** Compose in the `@main` App (the composition root); pass `.live` clients down. Tests pass `.mock`.
- **Ownership wiring:** `@State` owns an `@Observable`; `let` receives read-only; `@Bindable` for two-way (`$`); `@Environment(Type.self)` for deeply shared state.
- `@AppStorage` lives **in Views only** — never inside an `@Observable` class (observation won't see it; use `UserDefaults` + a `didSet` instead).

Folder layout:

```
CoreKit/                      # SPM package — Foundation only, Linux-testable
  Sources/
    Networking/              # APIClient, Endpoint, NetworkError, middleware
    Models/                  # Decodable+Sendable wire models, JSONDecoder.api
  Tests/
    NetworkingTests/         # incl. integration tests vs a live local server
    ModelsTests/
App/
  App.swift                  # @main composition root: builds .live clients
  Features/
    Trips/                   # TripStore, TripsView, TripRow  (one folder per feature)
    Settings/
  Navigation/                # AppTab enum, Router, route + sheet enums
  Shared/                    # ViewModifiers, Environment keys, design tokens
```

---

## 5. Navigation

TabView shell, one independent `NavigationStack` per tab. Routes are `Hashable` enums; routers are `@MainActor @Observable`.

```swift
enum AppTab: Hashable { case home, search, profile }

struct MainTabView: View {
    @State private var selectedTab: AppTab = .home

    var body: some View {
        TabView(selection: $selectedTab) {
            Tab("Home", systemImage: "house", value: .home) {
                NavigationStack { HomeView() }
            }
            Tab("Search", systemImage: "magnifyingglass", value: .search) {
                NavigationStack { SearchView() }
            }
            Tab("Profile", systemImage: "person", value: .profile) {
                NavigationStack { ProfileView() }
            }
        }
    }
}
```

Rules:
- Use the **`Tab(value:)` API with `TabView(selection:)`** — not `.tabItem`. Use `NavigationStack`, never `NavigationView`.
- **Each tab owns its own `NavigationPath`** (a per-tab router). Never share one path across tabs.
- Map routes with `.navigationDestination(for: Route.self)`. Store lightweight `Hashable` route data in the path, never view instances.
- **Sheets:** `.sheet(item:)` over `.sheet(isPresented:)` when state is a model; the sheet owns its `dismiss()`. Size with `.presentationSizing(.form)`, don't hardcode frames.
- Deep links: centralize URL parsing in the router (`.onOpenURL` → `router.handle(url:)`), validate before navigating.

---

## 6. Swift Testing (Linux-clean, Foundation only)

Use the **Swift Testing** framework (`import Testing`) — `@Test`/`@Suite`/`#expect`/`#require`. Package tests must **not** import UIKit/SwiftUI/XCUITest so they run on Linux. Test models, decoding, and the client; don't test views in the package.

```swift
import Testing
import Foundation
@testable import Models

@Test("Decodes snake_case + ISO date, falls back on unknown enum")
func decodesEvent() throws {
    let json = Data("""
    {"event_id":"e1","start_time":"2026-06-20T10:00:00Z","status":"archived"}
    """.utf8)
    let event = try JSONDecoder.api.decode(Event.self, from: json)
    #expect(event.eventID == "e1")
    #expect(event.status == .unknown)        // forward-compatible
}
```

Unit-test the client against `URLProtocol`, not by mocking `URLSession`. For **integration tests, hit a live local HTTP server** (Foundation only, works on Linux — no UIKit):

```swift
import Testing
import Foundation
@testable import Networking

@Suite(.serialized)                          // shared port/server → serialize
struct APIClientIntegrationTests {
    @Test func fetchDecodesFromLiveServer() async throws {
        let server = try LocalHTTPServer { _ in
            (200, Data(#"{"items":[{"id":1,"display_name":"Paris"}]}"#.utf8))
        }
        defer { server.stop() }

        let client = APIClient(baseURL: server.baseURL, decoder: .api)
        let trips = try await client.fetch([Trip].self, .trips)
        #expect(trips.first?.displayName == "Paris")
    }
}
```

> `LocalHTTPServer` is a tiny Foundation-only test helper built on a `Network`-free `SocketPort`/POSIX socket listener (or any cross-platform Swift HTTP lib) that binds `127.0.0.1:0` and returns a canned response. Keep it in the test target so it never ships.

Testing rules:
- Name tests by behavior: `fetchReturnsNoConnectionWhenOffline`, not `testFetch`.
- `#require` when later assertions depend on a value; `#expect` for independent checks.
- Tests run in parallel by default — each test sets up its own state. Use `@Suite(.serialized)` **only** for genuinely shared external state (the live server, a temp file), not to express ordering.
- Test error paths and cancellation explicitly. No `Task.sleep` for synchronization — use `confirmation` or injected clocks.
- Mocks conform to the protocol (`APIClientProtocol`), never subclass concrete types.
- Exit tests (`fatalError` paths) are unavailable on iOS targets — test fatal logic through smaller non-exiting APIs.

---

## 7. Top gotchas

1. **`.convertFromSnakeCase` is spelling-based and breaks on acronyms.** `image_url`→`imageUrl` ≠ `imageURL`. Any `URL`/`ID`/`URI` property needs explicit `CodingKeys`. This silently fails to decode otherwise.
2. **URLSession does not throw on 4xx/5xx.** Always check `HTTPURLResponse.statusCode` before decoding, or you'll decode an error body as a success model.
3. **`@AppStorage` inside `@Observable` is invisible to observation** — views won't update. Keep `@AppStorage` in Views; use `UserDefaults` + `didSet` inside `@Observable` classes.
4. **`@MainActor` on every `@Observable` UI model is mandatory** for Swift 6 data-race safety — but keep it *off* the networking/model package so it stays Linux-portable and reusable. Split isolation (some `@MainActor`, some `nonisolated` members in one type) is a bug.
5. **Stored-property defaults don't satisfy `Decodable` for missing keys**, and missing enum cases throw — use `decodeIfPresent ?? default` and an `unknown` enum fallback for any forward-compatible Google JSON.
6. **Liquid Glass / iOS 26 APIs need `if #available(iOS 26, *)` gates** with `.ultraThinMaterial` fallbacks; apply `.glassEffect()` *after* layout modifiers, and don't nest `GlassEffectContainer`s.
```