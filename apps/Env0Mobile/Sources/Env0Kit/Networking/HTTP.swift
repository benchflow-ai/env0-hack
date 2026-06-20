import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// HTTP verbs used by the env-0 mock Google APIs.
public enum HTTPMethod: String, Sendable {
    case get = "GET"
    case post = "POST"
    case patch = "PATCH"
    case put = "PUT"
    case delete = "DELETE"
}

/// A single request expressed relative to a service base URL.
///
/// Endpoints are value types so services can build them cheaply and tests can
/// assert on them without hitting the network. The actual `URL` is resolved
/// against a base URL by ``url(relativeTo:)`` at send time.
public struct Endpoint: Sendable, Equatable {
    public var path: String
    public var method: HTTPMethod
    public var queryItems: [URLQueryItem]
    public var headers: [String: String]
    public var body: Data?

    public init(
        _ path: String,
        method: HTTPMethod = .get,
        query: [URLQueryItem] = [],
        headers: [String: String] = [:],
        body: Data? = nil
    ) {
        self.path = path
        self.method = method
        self.queryItems = query
        self.headers = headers
        self.body = body
    }

    /// Resolve the absolute URL for this endpoint against `baseURL`.
    ///
    /// `path` may itself contain a leading slash; it is appended to the base
    /// path. Query items are only attached when non-empty so we never emit a
    /// dangling `?`.
    public func url(relativeTo baseURL: URL) -> URL? {
        let trimmed = path.hasPrefix("/") ? String(path.dropFirst()) : path
        guard var components = URLComponents(
            url: baseURL.appendingPathComponent(trimmed),
            resolvingAgainstBaseURL: true
        ) else { return nil }
        if !queryItems.isEmpty {
            components.queryItems = queryItems
        }
        return components.url
    }
}

extension URLQueryItem {
    /// Convenience that drops the item entirely when the value is nil, so
    /// callers can build optional query params inline.
    static func optional(_ name: String, _ value: String?) -> URLQueryItem? {
        value.map { URLQueryItem(name: name, value: $0) }
    }
}
