import Foundation

public extension GmailMessage {
    /// Case-insensitive lookup of an RFC2822 header on the top-level payload.
    func headerValue(_ name: String) -> String? {
        payload?.headers?.first { $0.name.caseInsensitiveCompare(name) == .orderedSame }?.value
    }

    var subject: String? { headerValue("Subject") }
    var from: String? { headerValue("From") }
    var to: String? { headerValue("To") }
    var cc: String? { headerValue("Cc") }

    /// Best timestamp: the server `internalDate` (epoch ms), falling back to the
    /// `Date:` header when absent.
    var bestDate: Date? {
        internalDateDate ?? headerValue("Date").flatMap(DateParsing.rfc3339)
    }

    /// Decoded plain-text body: the first `text/plain` part (recursing into
    /// multipart), falling back to any `text/*` part.
    var bodyText: String? {
        payload?.firstTextBody()
    }

    /// True when any part advertises a filename (a crude "has attachment" signal).
    var hasAttachment: Bool {
        payload?.containsAttachment() ?? false
    }
}

extension GmailMessagePart {
    /// Recursively find the best human-readable text body.
    func firstTextBody() -> String? {
        if mimeType == "text/plain", let text = body?.decodedText() {
            return text
        }
        if let parts {
            for part in parts {
                if let text = part.firstTextBody() { return text }
            }
        }
        if mimeType?.hasPrefix("text/") == true, let text = body?.decodedText() {
            return text
        }
        return nil
    }

    func containsAttachment() -> Bool {
        if let filename, !filename.isEmpty { return true }
        return parts?.contains { $0.containsAttachment() } ?? false
    }
}

extension GmailMessagePartBody {
    /// Decode the base64url body `data` into UTF-8 text.
    func decodedText() -> String? {
        guard let data = decodedData() else { return nil }
        return String(decoding: data, as: UTF8.self)
    }

    func decodedData() -> Data? {
        guard let data, !data.isEmpty else { return nil }
        return Data(base64URLEncoded: data)
    }
}

extension Data {
    /// Decode a base64url string (with or without `=` padding).
    init?(base64URLEncoded string: String) {
        var normalized = string
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        while normalized.count % 4 != 0 { normalized.append("=") }
        guard let decoded = Data(base64Encoded: normalized) else { return nil }
        self = decoded
    }
}
