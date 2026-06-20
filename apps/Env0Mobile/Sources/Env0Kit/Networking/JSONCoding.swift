import Foundation

/// Shared JSON encoder/decoder factory.
///
/// Google REST JSON is already camelCase, so we deliberately keep the default
/// key strategy (no `.convertFromSnakeCase`) and let Swift property names match
/// the wire field names 1:1. Dates are intentionally *not* handled with a global
/// `dateDecodingStrategy` because the suite mixes formats per field — Gmail uses
/// epoch-millisecond strings, Calendar uses RFC3339, Drive uses RFC3339 with
/// fractional seconds. Models keep the raw string and expose a parsed `Date`
/// via ``DateParsing``.
public enum JSONCoding {
    public static func makeDecoder() -> JSONDecoder {
        JSONDecoder()
    }

    public static func makeEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.withoutEscapingSlashes]
        return encoder
    }
}

/// Date parsing helpers for the formats the env-0 suite emits.
public enum DateParsing {
    /// Parse an RFC3339 timestamp, tolerating optional fractional seconds.
    /// Handles both `2026-06-20T10:00:00Z` and `2026-06-20T10:00:00.123Z`.
    public static func rfc3339(_ string: String?) -> Date? {
        guard let string, !string.isEmpty else { return nil }
        if let date = rfc3339Fractional.date(from: string) { return date }
        return rfc3339Plain.date(from: string)
    }

    /// Parse an epoch-millisecond value delivered as a string (Gmail
    /// `internalDate`) or a number.
    public static func epochMillis(_ string: String?) -> Date? {
        guard let string, let millis = Double(string) else { return nil }
        return Date(timeIntervalSince1970: millis / 1000)
    }

    /// Parse an all-day calendar `date` value (`YYYY-MM-DD`, no time zone).
    /// All-day events are infrequent, so the formatter is built per call to
    /// stay `Sendable`-clean on every platform.
    public static func calendarDay(_ string: String?) -> Date? {
        guard let string else { return nil }
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.date(from: string)
    }

    // Configured once and then only used for thread-safe `date(from:)` parsing,
    // so the shared instances are safe to read concurrently.
    nonisolated(unsafe) private static let rfc3339Fractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    nonisolated(unsafe) private static let rfc3339Plain: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

}
