import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// Abstraction over the transport so services can be unit-tested against a stub
/// without touching the network. Conformers only have to implement
/// ``data(for:)``; decoding/discarding helpers come from the extension below.
public protocol Env0Requesting: Sendable {
    /// Raw bytes of a 2xx response, or throws ``Env0Error``.
    func data(for endpoint: Endpoint) async throws -> Data
}

public extension Env0Requesting {
    /// Execute and decode the response body as `T`.
    func get<T: Decodable & Sendable>(_ type: T.Type, _ endpoint: Endpoint) async throws -> T {
        let data = try await data(for: endpoint)
        do {
            return try JSONCoding.makeDecoder().decode(T.self, from: data)
        } catch {
            throw Env0Error.decoding(String(describing: error))
        }
    }

    /// Execute and discard the body (deletes, label mutations, …).
    @discardableResult
    func run(_ endpoint: Endpoint) async throws -> Data {
        try await data(for: endpoint)
    }
}

/// `URLSession`-backed implementation of ``Env0Requesting`` for a single
/// service base URL. One instance per service (Gmail, Calendar, …); all share
/// an injected `URLSession`.
///
/// Marked `@unchecked Sendable`: the stored `URLSession` is thread-safe for the
/// concurrent request pattern used here, and a fresh `JSONDecoder` is created
/// per call rather than shared.
public struct Env0APIClient: Env0Requesting, @unchecked Sendable {
    public let baseURL: URL
    private let session: URLSession
    private let defaultHeaders: [String: String]

    public init(
        baseURL: URL,
        session: URLSession = Env0APIClient.makeSession(),
        defaultHeaders: [String: String] = [:]
    ) {
        self.baseURL = baseURL
        self.session = session
        self.defaultHeaders = defaultHeaders
    }

    public func data(for endpoint: Endpoint) async throws -> Data {
        guard let url = endpoint.url(relativeTo: baseURL) else {
            throw Env0Error.invalidURL(endpoint.path)
        }
        var request = URLRequest(url: url)
        request.httpMethod = endpoint.method.rawValue
        for (key, value) in defaultHeaders { request.setValue(value, forHTTPHeaderField: key) }
        for (key, value) in endpoint.headers { request.setValue(value, forHTTPHeaderField: key) }
        if let body = endpoint.body {
            request.httpBody = body
            if request.value(forHTTPHeaderField: "Content-Type") == nil {
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            }
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch let urlError as URLError {
            throw Env0Error.transport(Self.describe(urlError))
        } catch is CancellationError {
            throw Env0Error.transport("cancelled")
        } catch {
            throw Env0Error.transport(error.localizedDescription)
        }

        guard let http = response as? HTTPURLResponse else {
            throw Env0Error.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            throw Env0Error.http(status: http.statusCode, message: Self.parseErrorMessage(from: data))
        }
        return data
    }

    /// A configured session with sensible timeouts; prefer this over
    /// `URLSession.shared` per the ios-networking guidance.
    public static func makeSession() -> URLSession {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 120
        #if !canImport(FoundationNetworking) // Apple platforms only
        config.waitsForConnectivity = true
        #endif
        config.httpAdditionalHeaders = ["Accept": "application/json"]
        return URLSession(configuration: config)
    }

    private static func parseErrorMessage(from data: Data) -> String? {
        if let envelope = try? JSONCoding.makeDecoder().decode(GoogleErrorEnvelope.self, from: data) {
            return envelope.error.message
        }
        let text = String(decoding: data, as: UTF8.self)
        return text.isEmpty ? nil : text
    }

    private static func describe(_ error: URLError) -> String {
        switch error.code {
        case .notConnectedToInternet, .networkConnectionLost: return "No network connection."
        case .timedOut: return "The request timed out."
        case .cancelled: return "cancelled"
        case .cannotFindHost, .cannotConnectToHost:
            return "Can't reach the env-0 server. Is it running and the base URL correct?"
        default: return error.localizedDescription
        }
    }
}
