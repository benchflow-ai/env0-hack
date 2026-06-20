# Verification status

What is proven, how, and what still requires a Mac. Built and verified on Linux
(Swift 6.1.2 toolchain) — no Xcode available here.

## Env0Kit core — fully verified on Linux ✅

| Check | Command | Result |
|---|---|---|
| Builds (Foundation-only) | `swift build` | Build complete |
| Unit tests (decode/encode/foundation/content) | `swift test` | 64 tests pass |
| **Live integration vs running mock servers** | `ENV0_INTEGRATION=1 swift test --filter Live` | 7 tests pass |

The live integration suite starts the real env-0 Gmail/Calendar/Docs/Drive
servers (`scripts/run_local_services.sh start`) and exercises the typed clients
end to end: list+read threads, star/unstar round-trip, list calendars + events,
create+read a doc, list+get Drive files, and all four `/health` probes. This is
the strongest available proof that the models match the wire format and the
services work against the actual mock world.

## SwiftUI app layer — verified as far as Linux allows ✅ (full type-check needs Xcode 26)

SwiftUI/UIKit cannot be compiled on Linux, so the app layer is verified by:

| Check | Method | Result |
|---|---|---|
| Syntax | `swiftc -frontend -parse` on all 21 App files | all parse OK |
| Env0Kit call correctness | every `suite.<svc>.<method>(` audited vs the services' public funcs | all match |
| Constructed types | every Env0Kit type built in the app has a `public init` (GmailCompose, EventWriteRequest, EventDateTime) | confirmed |
| Model access | every model property/enum case used (Drive permission roles/types, DriveFile fields, attendee fields, message helpers) audited vs Env0Kit | all match |
| Cross-references | every referenced view/type defined exactly once; no duplicate top-level type names | confirmed |
| API correctness | adversarial multi-agent review against the swift-ios-skills (navigation, Liquid Glass, patterns, concurrency) | see git history |

**Remaining gap:** full Swift type-checking of the SwiftUI views (modifier
signatures, generic inference, iOS 26 SDK symbols) requires building with Xcode
26 on macOS — `xcodegen generate && xcodebuild`. Everything checkable without the
iOS SDK has been checked.

## Reproduce

```bash
cd apps/Env0Mobile
swift build && swift test                              # core, Linux
./scripts/run_local_services.sh start
ENV0_INTEGRATION=1 swift test --filter Live            # core vs live servers
# app syntax gate (Linux):
find App -name '*.swift' -exec swiftc -frontend -parse {} \;
# full app build (macOS, Xcode 26):
xcodegen generate && xcodebuild -scheme Env0Mobile -destination 'generic/platform=iOS Simulator'
```
