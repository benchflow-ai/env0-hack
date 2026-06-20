import SwiftUI

/// Four-state async value used by every feature store: idle → loading → loaded
/// / failed. Keeps the previous value while reloading so lists don't flash.
public enum Loadable<Value: Sendable>: Sendable {
    case idle
    case loading
    case loaded(Value)
    case failed(String)

    public var value: Value? {
        if case .loaded(let value) = self { return value }
        return nil
    }

    public var isLoading: Bool {
        if case .loading = self { return true }
        return false
    }

    public var errorMessage: String? {
        if case .failed(let message) = self { return message }
        return nil
    }
}

/// Renders the right view for a ``Loadable`` state: a spinner while loading
/// (with nothing yet), the content when loaded, a retry-able error, or an empty
/// state. Use it as the body of every feature list/detail.
public struct LoadableView<Value: Sendable, Content: View>: View {
    private let state: Loadable<Value>
    private let retry: (() -> Void)?
    private let content: (Value) -> Content

    public init(
        _ state: Loadable<Value>,
        retry: (() -> Void)? = nil,
        @ViewBuilder content: @escaping (Value) -> Content
    ) {
        self.state = state
        self.retry = retry
        self.content = content
    }

    public var body: some View {
        switch state {
        case .idle, .loading:
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        case .loaded(let value):
            content(value)
        case .failed(let message):
            ContentUnavailableView {
                Label("Something went wrong", systemImage: "exclamationmark.triangle")
            } description: {
                Text(message)
            } actions: {
                if let retry {
                    Button("Try Again", action: retry).buttonStyle(.glassProminent)
                }
            }
        }
    }
}
