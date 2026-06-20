// swift-tools-version: 6.0
import PackageDescription

// Env0Kit is the platform-agnostic core of the Env0 Mobile app: typed clients +
// Codable models for the env-0 mock Google Workspace suite (Gmail, Calendar,
// Docs, Drive). It depends only on Foundation, so it builds and tests on Linux
// (CI / agents) as well as on Apple platforms. The SwiftUI app target lives in
// ../App and is assembled into an Xcode project via project.yml (XcodeGen).
let package = Package(
    name: "Env0Kit",
    platforms: [
        .iOS(.v17),
        .macOS(.v13),
    ],
    products: [
        .library(name: "Env0Kit", targets: ["Env0Kit"]),
    ],
    targets: [
        .target(
            name: "Env0Kit",
            swiftSettings: [
                .enableUpcomingFeature("StrictConcurrency"),
            ]
        ),
        .testTarget(
            name: "Env0KitTests",
            dependencies: ["Env0Kit"]
        ),
    ]
)
