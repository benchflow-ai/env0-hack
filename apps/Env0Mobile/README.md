# Env0 Mobile

A SwiftUI iOS app that packs the **env-0 mock Google Workspace suite** — Gmail,
Calendar, Docs, and Drive — into one mobile interface. It's the "demo frontend"
from the HUD brief and a surface for exercising small on-device agents against
the mock world.

env-0 mirrors the real Google REST wire format, so this app talks to a local
env-0 deployment exactly the way it would talk to `googleapis.com` — the only
difference is the base URL.

```
┌─────────────────────────── Env0 Mobile (iOS 26, SwiftUI) ───────────────────────────┐
│  Mail        Calendar       Docs          Drive          Settings                    │
│  threads     events/RSVP    read/edit     browse/preview host + health               │
└───────────────────────────────────┬──────────────────────────────────────────────────┘
                                     │  Env0Kit  (Foundation-only, Linux-testable)
                  ┌──────────────────┴───────────────────┐
            GmailService  CalendarService  DocsService  DriveService
                  │            │              │            │
            :9001        :9003          :9004        :9005      ← env-0 mock services (HTTP)
```

## Layout

```
apps/Env0Mobile/
  Package.swift              # Env0Kit SwiftPM library (+ tests) — builds on Linux & macOS
  Sources/Env0Kit/          # the platform-agnostic core
    Networking/             # Env0APIClient (URLSession async/await), Env0Error, Endpoint, JSON/date coding
    Models/                 # Codable+Sendable wire models (Gmail/Calendar/Docs/Drive)
    Services/               # Gmail/Calendar/Docs/Drive services + Env0Suite aggregator
    Configuration/          # Env0Environment (per-service base URLs)
  Tests/Env0KitTests/       # unit (decode/encode) + opt-in live integration tests
  App/                      # the SwiftUI app (built with Xcode 26)
    Env0MobileApp.swift     # @main composition root
    AppSettings.swift       # @Observable: host + live Env0Suite + health
    RootView.swift          # 5-tab Liquid Glass shell
    Shared/                 # Loadable + LoadableView, Theme, glass helpers
    Features/{Mail,Calendar,Docs,Drive,Settings}/
  project.yml               # XcodeGen spec (no committed .xcodeproj)
  scripts/run_local_services.sh
  docs/                     # captured API specs, iOS house style, ADRs
```

## Run the backend (the four mock services)

```bash
# from apps/Env0Mobile
./scripts/run_local_services.sh start    # seed + serve gmail/gcal/gdoc/gdrive on 9001/9003/9004/9005
./scripts/run_local_services.sh health   # curl each /health
./scripts/run_local_services.sh stop
```

## Build & run the app (macOS, Xcode 26)

```bash
brew install xcodegen
cd apps/Env0Mobile
xcodegen generate          # produces Env0Mobile.xcodeproj from project.yml
open Env0Mobile.xcodeproj  # run on an iOS 26 Simulator
```

In the **Settings** tab, set the host (`127.0.0.1` from the Simulator, or your
Mac's LAN IP from a device) and tap **Apply & Test Connection** — the four
services should report Online.

> ATS is relaxed (`NSAllowsLocalNetworking` / `NSAllowsArbitraryLoads`) because
> this is a developer client for local plain-HTTP mock servers. See
> [`docs/adr-0001-reuse-strategy.md`](docs/adr-0001-reuse-strategy.md).

## Verify the core on Linux (no Mac needed)

`Env0Kit` is Foundation-only, so the whole networking + model layer builds and
tests without Xcode:

```bash
cd apps/Env0Mobile
swift build
swift test                                   # unit tests only
# live integration tests against running servers:
./scripts/run_local_services.sh start
ENV0_INTEGRATION=1 swift test --filter Live
```

## How it was built

- **Reuse first** ("ponytail"): build on the Google REST wire contract env-0
  already mirrors, plus URLSession/Codable/Swift Testing/SwiftPM/XcodeGen — no
  third-party runtime deps. Rationale in
  [`docs/adr-0001-reuse-strategy.md`](docs/adr-0001-reuse-strategy.md).
- **iOS engineering** follows the
  [swift-ios-skills](https://github.com/dpearson2699/swift-ios-skills)
  playbook (networking, Codable, concurrency, architecture, navigation, Liquid
  Glass, Swift Testing) — distilled in
  [`docs/ios-house-style.md`](docs/ios-house-style.md).
- Per-service API contracts are captured in [`docs/api-specs/`](docs/api-specs/).
```
