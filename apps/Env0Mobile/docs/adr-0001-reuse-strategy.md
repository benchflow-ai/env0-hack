# ADR 0001 — Reuse strategy: build on existing contracts, write minimal glue

Status: accepted · 2026-06-20

## Context

We need an iOS app that packages the env-0 mock Google Workspace suite (Gmail,
Calendar, Docs, Drive) into one mobile interface — the "demo frontend" in the
HUD brief, and a surface for exercising small on-device agents against the mock
world. The directive was explicit: **find reusable open source first; don't
build from scratch.** env-0 itself mirrors the *real* Google REST wire format,
so an agent "points at localhost:9001 instead of googleapis.com with zero code
changes."

## Options considered

### 1. GoogleAPIClientForREST (GTLR) + GoogleSignIn / GTMAppAuth
The official, mature Swift/ObjC clients for Gmail/Calendar/Drive (Docs has no
first-party Swift client).

- ➕ Battle-tested, generated from the same discovery docs env-0 mimics.
- ➖ OAuth/sign-in centric. The env-0 mocks run with **auth disabled by
  default** (no Bearer token); GTLR's `GTLRService`/`GTMSessionFetcher` stack is
  built around real Google sign-in and assumes HTTPS + token refresh.
- ➖ Pointing it at a plain-HTTP `localhost`/LAN host means overriding
  `rootURLString` *and* defeating its auth + ATS assumptions — fighting the
  library instead of using it.
- ➖ Large generated surface and an ObjC dependency for what is, against the
  mock, a handful of endpoints per service. No Docs coverage at all.
- ➖ Does not build/test on Linux, so we'd lose the ability to verify the core
  in CI / agent sandboxes.

### 2. Thin typed client over the documented mock endpoints (URLSession + Codable)
Treat **the Google REST wire contract as the reusable asset** (it is — env-0
reproduces it, and it's documented in `docs/api-specs/`). Write the minimum
typed Swift glue on top of the platform's own networking.

- ➕ Foundation-only → the whole core (`Env0Kit`) builds and tests on Linux,
  including integration tests against the live mock servers.
- ➕ No third-party runtime dependencies; swapping the base URL is the only
  difference between mock and production.
- ➕ Small, reviewable, and shaped exactly to what the four services expose.
- ➖ We own the model/endpoint code (mitigated: it's generated from the captured
  wire spec and covered by decode + live integration tests).

### 3. A third-party networking library (Alamofire / Moya)
- ➖ Rejected. Per the `ios-networking` skill, URLSession async/await closes the
  ergonomic gap that justified these; adding one is over-building.

## Decision

**Reuse at the contract and platform level; write the minimum glue (the
"ponytail" principle).**

Concretely, we reuse:
- **The Google REST wire contract** that env-0 mirrors — captured per service in
  `docs/api-specs/` and modelled 1:1 in `Env0Kit`.
- **The platform's batteries:** `URLSession` (async/await) for transport,
  `Codable` for models, **Swift Testing** for tests, **SwiftPM** for the core
  package — no third-party runtime deps.
- **XcodeGen** (open source) to generate the Xcode project from `project.yml`,
  so no binary `.xcodeproj` is committed.
- **dpearson2699/swift-ios-skills** as the engineering playbook (networking,
  Codable, concurrency, architecture, navigation, Liquid Glass, testing).
- **SwiftUI's native components** for the UI — no UI component libraries.

We write only the typed glue: `Env0Kit` (a protocol-fronted async client, four
typed services, Codable wire models) and a SwiftUI app shell.

## Consequences

- `Env0Kit` is Foundation-only and **Linux-verifiable** — `swift test` runs unit
  decode tests and live integration tests against seeded mock servers without a
  Mac.
- Mock ↔ production is a one-line base-URL change (`Env0Environment`), preserving
  env-0's "same wire format" property.
- If we ever target *real* Google endpoints with OAuth, the documented migration
  path is to slot GTLR (or our client + `GTMAppAuth`) behind the existing
  `Env0Requesting` protocol — the services and UI are unaffected.
- We accept ownership of the wire models, bounded by the captured spec and
  enforced by decode + integration tests.
