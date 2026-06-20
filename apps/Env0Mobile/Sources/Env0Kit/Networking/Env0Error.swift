import Foundation

/// Typed errors surfaced by ``Env0APIClient``.
///
/// Associated values are kept `Sendable`/`Equatable` (strings, not `Error`
/// existentials) so the type can cross actor boundaries and be asserted in
/// tests. Transport and decoding failures carry a human-readable description
/// rather than the original error to preserve those conformances.
public enum Env0Error: Error, Sendable, Equatable {
    /// The endpoint could not be turned into a valid URL.
    case invalidURL(String)
    /// The response was not an `HTTPURLResponse`.
    case invalidResponse
    /// A non-2xx status. `message` is parsed from the Google-style error
    /// envelope (`{ "error": { "message": ... } }`) when present.
    case http(status: Int, message: String?)
    /// JSON decoding failed; the string is the decoding error's description.
    case decoding(String)
    /// A transport-level failure (offline, timeout, cancelled, …).
    case transport(String)

    public var isCancellation: Bool {
        if case .transport(let s) = self { return s.contains("cancelled") }
        return false
    }
}

extension Env0Error: LocalizedError {
    public var errorDescription: String? {
        switch self {
        case .invalidURL(let s): return "Invalid URL: \(s)"
        case .invalidResponse: return "The server returned an unexpected response."
        case .http(let status, let message):
            if let message { return "HTTP \(status): \(message)" }
            return "HTTP \(status)"
        case .decoding(let s): return "Could not read the server response: \(s)"
        case .transport(let s): return s
        }
    }
}

/// The error envelope Google REST APIs (and the env-0 mocks) return on failure.
struct GoogleErrorEnvelope: Decodable {
    struct Body: Decodable {
        let code: Int?
        let message: String?
        let status: String?
    }
    let error: Body
}
