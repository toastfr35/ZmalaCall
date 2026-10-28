# Deep component code review

Baseline: 3ae70dd (v0.3.24), 28 October 2026. Checkout: W:/git/zmala.

This is a review plan and evidence record, not a product specification. Review
server, Android app and Pi terminal in that order. Keep existing user workflows
unless a demonstrated defect requires a correction.

## Plan

- [x] Server: inventory authored modules; inspect persistence and shutdown,
  identity and permissions, enrollment/configuration, SIP and media lifecycle,
  callbacks/push, maintenance and browser controllers. Identify duplication,
  expensive repeated work, ambiguous ownership and unsupported documentation.
  Refactor focused boundaries; verify failure paths and cache invalidation.
- [x] Android: inspect service/core and Activity lifecycle, asynchronous work,
  enrollment/networking, contacts/callbacks, media controls and updates. Simplify
  ownership, cancellation and repeated logic; test stale and concurrent results.
- [x] Terminal: inspect engine/state flow, input/navigation, network/configuration,
  audio/video and peripheral lifecycle, portraits/cache, TV/setup and maintenance.
  Separate responsibilities where useful and verify recovery/cleanup paths.
- [x] Reconcile affected Doorstop items and direct verification plans, code trace
  comments and technical/user documentation. Regenerate derived artifacts.
- [x] Run component tests, lint, requirements and relevant integration checks.
  Document physical-device limits separately from automated evidence.
- [x] Inspect the final diff for regressions/private files and raise the release version.
- GitHub issue #35 and its linked PR record Verify, merge and release completion;
  merge only after required checks, then verify the tag and all nine release assets.

## Review decisions and evidence

Record concrete findings and the reason for each change below as work proceeds.
Comments should explain invariants, lifetime and non-obvious decisions rather
than restating the code. Avoid cosmetic splitting or new abstractions without a
clear responsibility, simpler callers or reduced repeated work.

### Server

Reviewed configuration/account derivations, snapshots and shutdown, HTTP authority
boundaries, SIP admission/dialogs, relay transactions, push-wake ownership, callback
state, backup recovery, photo conversion, maintenance leases and browser controllers.

- Extracted `ContactDirectory`: phone reads now share the revision cache used by
  terminals; one collator is reused and returned rows remain detached. Regression
  checks cover both readers, edits, group revocation and secret/live-field isolation.
- Extracted SIP dialog forwarding into `sip-dialogs.js`. Admission/peer ownership
  remains in `SipServer`; staged media and response ordering stay together. Existing
  cancellation, late-response, negotiation and HMAC regression checks pass.
- Protected account identity changes/deletion/reassociation during push wakeup,
  before the call has a SIP dialog. This prevents administrative edits disrupting
  pending calls; it is not a claim that the previous code bypassed authentication.
- Corrected callback History prose in UI, requirements and the guide source: expiry
  removes records; History retains completed/cancelled requests.
- Retained the existing atomic persistence, backup transaction and async conversion
  boundaries. No new caching of credentials or broad inheritance hierarchy.

### Android

Reviewed Activity/CallSession/CallService ownership, core setup and callbacks,
background refresh, push/callback reconciliation, update staging/commit gates,
portrait work, preview geometry and control rendering.

- Extracted `PortraitLoader` with an 8 MiB decoded bitmap cache. Directory refreshes
  reuse portraits; enrollment changes clear them. Generation checks reject stale
  results before cache publication and display. Images remain static on Android.
- Repeated service starts reuse one renewable wake lock instead of orphaning the
  earlier lock until timeout. Destruction cancels renewal and releases ownership.
- Separated the original call-control glyphs from gesture/layout/lifecycle code.
- Preserved update signing/idle-call gates, media configuration and visible workflows.
  JVM tests/build passed; emulator lifecycle/cache/control checks passed (physical
  audio/video and vendor power-policy qualification are separate).

### Terminal

Reviewed native engine setup/call ownership/diagnostics, configuration polling and
revision dispatch, call/preflight input paths, carousel/volume, maintenance leases,
USB/audio wake controllers, TV visibility checks and portrait loading/animation.

- Separated byte validation from the photo download scheduler. Replaced contact lists
  prune queued obsolete requests; late obsolete downloads cannot publish or retry.
  Contact order now determines initial scheduling instead of set iteration order.
- Extracted media snapshot collection from `Engine`. Native statistics references
  are released in a `finally` block even if a getter fails; unavailable values still
  stay omitted and diagnostics do not open devices.
- Kept hardware timing, C20 routing, click buffering and TV controls unchanged. This
  review does not claim a new physical-device/call qualification.

### Validation record

- `make lint` and `make requirements` passed; no missing direct requirement test links.
- Server LLT: 180 passed, one browser/display skip subsequently passed in Chromium.
  Server HLT: 47 passed, four display skips; targeted Chromium browser/controller
  integration passed. An intermittent Windows forbidden ephemeral port exposed by
  migration HLT was fixed using a shared fetch-safe listener helper; HLT rerun passed.
- Python server LLT: 12 passed. Terminal LLT: 511 passed, 11 platform skips.
  The 24 Python HLT scenarios requiring Linux/display were skipped on Windows;
  GitHub's portable job owns the Linux/Xvfb run.
- Android: 31 JVM tests, debug build and lint passed. Eighteen emulator scenarios
  passed across portraits, wake ownership, call controls, contacts, call continuity,
  update installation and callback notifications. After tighter bitmap sampling,
  all three portrait tests passed again (reuse, identity/stale isolation, eviction).
- The server Word guide retained 91 paragraphs with just the corrected callback
  History sentence changed. Its nine rendered pages and the regenerated PDF were
  inspected; the PDF guide has three pages and installation remains five pages.
- No Pi installation, physical handset, camera/audio or real network call was run.
  Existing hardware qualification records remain historical, not evidence for this run.
