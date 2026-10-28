# Component alignment review

Review baseline: `5450c4a` (28 October 2026). Work in `W:/git/zmala`.

Review and repair each component in order: server, Android app, then Pi terminal.
This is a code/documentation review record, not a new product specification.
Normative behavior remains in `requirements/`.

## Method and scope

For each component, inspect its authored source inventory, all themed HLR/LLR
records and implementation traces, linked verification plans/assertions, technical
guide and affected user-guide sources. Check boundaries, failure behavior,
lifecycle ownership and configuration defaults as well as ordinary success paths.
Record concrete mismatches before changing them, keep reciprocal links current,
and add regression assertions where behavior is corrected. Exclude third-party
dependencies and generated bundles from manual editing; regenerate derived files.

Automated tests establish only their asserted scope. Hardware, acoustic, real
network and long-running qualification are recorded separately and are not
inferred from a passing unit test or requirement-link validator.

## Sequence

- [x] Establish source/requirement inventory and baseline checks.
- [x] Server: startup/shutdown; authentication/host policy; accounts/enrollment;
  configuration/presence; SIP/media/messages; callbacks/push; persistence/backup;
  maintenance; administration UI and guides. Fix and verify before app review.
- [x] Android: enrollment/API; core/service/calls; notifications/callbacks;
  contacts/media controls; update/install lifecycle; manifest and guides.
  Fix and verify before terminal review.
- [x] Pi terminal: startup/setup/network; configuration/state; remote/navigation;
  audio/video/calls; portraits/UI/languages; callbacks/history; TV/power;
  maintenance/host policy and guides. Fix and verify.
- [x] Regenerate affected assets/guides; validate requirements and traces;
  run relevant full suites and inspect the final diff for private data.
- [ ] Bump Android version, submit PR, resolve Verify failures, merge only after
  required checks pass, and verify the resulting nine-asset release.

## Findings and evidence

### Server

Reviewed the authored server modules and browser controllers against all 16 server
requirement themes, their linked tests, deployment/runtime boundaries and the
technical guide. Baseline lint, portable suites and requirement-link checks passed;
that did not detect the following behavior and prose gaps.

Fixed:

- Restore omitted in-flight Firebase callback delivery from its busy checks.
- Account conversion failed to cancel the retired requester's callbacks; command
  retirement waited for a later poll instead of its mutation acknowledgement.
- Callback and command history trimming ran only on creation, allowing more than
  200 completed records after a full pending queue finished.
- SIP expiry clamping accepted infinite numeric inputs as valid registrations.
- Shutdown did not wait for callback delivery results before its final flush.
- Terminal association used the latest polling revision instead of the form's
  opening revision. Late dialog errors could target removed UI elements.
- The callback page incorrectly said Android notifications were unsupported and
  that terminal reminders required both people to be online.
- Backup previews counted private ringtones as pictures.
- The technical guide described obsolete installer artifacts, omitted callback
  push, duplicated enrollment instructions and did not qualify LAN-only ICE and
  plaintext rules. The server Word guide already describes the current notification,
  portrait and installation workflows. The later readability pass simplified these
  workflows while retaining their behavior.

Evidence: four targeted regression failures reproduced before their fixes;
32 lifecycle/storage/route cases and 22 UI cases passed afterward; shutdown and
callback delivery tests passed. Full server JavaScript run: 224 pass, five explicit
platform skips. The Linux run passed all 178 JavaScript unit and 51 integration
cases, including real browser interaction and responsive layouts; 12 Python unit
cases passed. Two privileged network scenarios were skipped in the local container.

### Android

Reviewed enrollment/API, native call/service ownership, push/callback histories,
update transport/installer, contact/call UI, manifest/resources and the Android
requirements. Fixed automatic installation rechecking the full thirty-second idle
window after interaction during staging. Corrected obsolete shutdown and icon-only
notice descriptions in the technical guide and a joined sentence in enrollment
requirements. Physical device behavior remains separately qualified.

App lint also identified overlapping JobScheduler ID ownership. Callback refreshes
now use a separate WorkManager range; a device assertion checks the initialized
configuration, not merely the application declaration.

Android evidence: JVM tests and lint pass. The emulator rerun passed 31 cases;
four explicitly conditional scenarios skipped and one background callback case
was blocked by the emulator losing Android network validation. Its scheduler
configuration, reconciliation and scope tests pass separately; the dependent
delivery case now explicitly declares and checks that prerequisite. Update UI
tests isolate unrelated fixture ring deadlines instead of depending on test order.

### Pi terminal

Reviewed the terminal source, themed requirements, implementation traces and
guides. Reproduced and fixed permanent maintenance authorization
rejections retaining results forever, and power-only TV qualification incorrectly
sending input-switch announcements. Corrected GIF path and obsolete motion
requirements. New tests fail on the previous implementations.

User-guide readability is included in this change: review all six Word sources,
the six derived PDFs and README, simplifying caller instructions and separating
helper setup from everyday actions. Render and inspect every updated guide.

Terminal focused evidence: 85 unit cases and 12 server status cases pass; native
worker, codec, preview and sanitizer scenarios pass in the matching Debian SDK
container. Expired running-core credentials now block new dial/answer. Read-only
media snapshots expose actual native counters through validated device reports.
Four remote child links were reviewed against the corrected button-only HLR before
clearing suspect flags; names, identity filtering, repeat handling and volume-overlay
children remain consistent. Hardware qualification remains outstanding as recorded
in astra.md.

## User documentation and final validation

Reviewed README and all six editable Word guides for audience, task order, literal
UI labels, prerequisites, recovery advice and print readability. Everyday terminal
calls now precede helper setup in the release guide. Phone instructions distinguish
QR images from PDFs, microphone mute from listening mute, incoming from outgoing
callbacks, and supported automatic updates from manual installation. Setup guides
retain connection diagrams and replace dense forwarding prose with a port table.
The authoring tool now separates guide copy from conversion and removes obsolete
one-off migrations. All six Word guides and all six generated PDFs were rendered
and visually inspected; external download links remain clickable.

Final local validation:

- `make lint`, `make test`, and `make requirements` pass on Windows. Requirement
  report: 248 mapped source files, 252 anchored LLRs, 227 plans and no missing links.
- Linux terminal unit suite: 520 cases, one platform skip; terminal integration:
  22 cases, two privileged/network skips. All display-runner scenarios pass.
  A stale setup fixture was corrected so normal UI ticks no longer log SDK-stub
  errors; its full display scenario passed again.
- Native codec, worker and preview checks, including undefined-behavior sanitizer,
  pass in the matching Debian SDK container.
- Android JVM tests, lint and emulator instrumentation pass: 31 executed cases and
  five explicitly conditional skips. No physical phone or Pi qualification is
  claimed; existing hardware limitations remain recorded in `astra.md`.
- Fifteen release/asset/version/credential-isolation tooling regressions pass.
- Android version is 0.3.23 / code 32, above main's 0.3.22 / code 31.

GitHub Verify and release publication are checked separately after submission.
