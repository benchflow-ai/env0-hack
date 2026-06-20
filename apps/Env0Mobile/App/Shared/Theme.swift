import SwiftUI

/// Lightweight design tokens. The app leans on system Liquid Glass for bars and
/// sheets (free on the iOS 26 SDK); these are just the per-service accent colors
/// and spacing the features share.
public enum Theme {
    public enum Spacing {
        public static let xs: CGFloat = 4
        public static let s: CGFloat = 8
        public static let m: CGFloat = 12
        public static let l: CGFloat = 16
        public static let xl: CGFloat = 24
    }

    /// One accent per env-0 service, used for tab tints and section headers.
    public static let mail = Color.red
    public static let calendar = Color.blue
    public static let docs = Color.indigo
    public static let drive = Color.green
}

/// A simple glass card surface for list rows / detail blocks.
public struct GlassCard<Content: View>: View {
    private let content: Content
    public init(@ViewBuilder content: () -> Content) { self.content = content() }

    public var body: some View {
        content
            .padding(Theme.Spacing.l)
            .glassEffect(.regular, in: .rect(cornerRadius: 16))
    }
}

public extension View {
    /// Wrap a view in regular Liquid Glass with a rounded-rect shape.
    func glassCard(cornerRadius: CGFloat = 16) -> some View {
        self.glassEffect(.regular, in: .rect(cornerRadius: cornerRadius))
    }
}
