# Automatic terminal application updates

Design and implementation plan for issue #113. This records the agreed approach;
implementation status is below. Runtime normative requirements will be added to
Doorstop with their implementation and reciprocal LLT/HLT plans. This document is
not evidence that update/recovery behavior is already available.

## Scope and experience

Automatic compatible Zmala application updates, applied as soon as practical.
No routine administrator approval. Background checks shortly after boot and at
staggered intervals; download/prepare without interrupting operation. Activate
after two minutes of safe inactivity initially, retry after ongoing use ends.
Server visibility is progress/reporting rather than an approval queue.

Explicitly excluded: OS releases, kernel, firmware, apt/system packages, dependency
upgrades and destructive shared-data migrations. An incompatible application
release is reported and skipped rather than modifying the host to accommodate it.
Existing enrollment, TV pairing, languages and settings remain persistent.

## Localized update screen

During activation, display a large, clear message in the terminal's selected
language, using its existing supported-language list and fonts. Background download
and preparation stay quiet. Proposed states: "Updating ZmalaCall. Please wait.",
"Checking the update. Please wait.", and "Restoring the previous version. Please
wait." Final wording and all supported translations are reviewed with layout tests.
No frozen percentage or estimated duration without a measurable basis.

A separate, unprivileged display process keeps this screen visible while the
application stops/restarts; it is not a child of the service being replaced.
Retain the existing display/compositor services. The selected validated locale is
captured before stopping the app and retained for recovery boot; missing/invalid
locale uses English. Large-text, CJK, RTL and long translated labels need visual
qualification. The candidate reports UI readiness behind the update overlay; only
confirmation removes it and makes normal controls available.

The update screen is rendered on HDMI without power/source commands: never wake
the TV or switch away from live TV solely for updating. If the user selects the
terminal input during activation, the message is already present. Recovery after
power loss displays the corresponding localized state when HDMI becomes available.
An update restart also preserves idle USB/camera sleep; qualification is passive.

## Ownership and admission

A stable root-owned updater/boot launcher lives outside application release slots.
Initial provisioning of that component belongs to the Pi installer. Its own future
replacement needs a separately designed recovery mechanism; application releases
cannot silently replace the recovery launcher or system services.

The ordinary app supplies status and requests, never arbitrary commands, URLs or
installation paths. The updater selects a verified release from the trusted feed.
Use narrow local IPC with peer authorization and bounded structured messages.

Before activation, obtain an exclusive maintenance lease through the app owner:
no ringing/connected/outgoing call, setup/scanning, settings write or TV setup.
Recheck immediately before stopping services. Advertise unavailable/updating to
the server and fence local dial/answer and remote call admission. A call already
starting wins; after the maintenance lease is granted, reject new calls cleanly.
An offline server does not bypass local fencing or prevent rollback. Lease expiry,
process crash and boot recovery cannot leave indefinite maintenance state.

## Package trust and compatibility

The release workflow produces an installation payload plus a signed manifest.
These are two additional machine-download assets alongside the existing nine
human-facing downloads; they are deployment files, not repository source archives.
A dedicated release signing key remains confined to the release workflow. The
terminal embeds trusted public keys; the server cannot authorize unsigned code.
Plan key rotation/revocation and recovery before enabling unattended updates.

The manifest binds version/sequence, package digest/size, architecture, OS baseline,
existing media ABI/dependency baseline, data-format compatibility and minimum
updater protocol. Reject unexpected downgrades; any emergency withdrawal/rollback
instruction is signed and bounded to an explicitly authorized confirmed release.
Validate TLS destinations/redirects and bound payload sizes, storage and retry rate.

Download to a temporary file, verify before unpacking, and extract safely into a
new candidate directory. Reject traversal, links, special files and duplicate
entries. Package-controlled install hooks are not executed as root. Native builds,
if needed against existing pinned host libraries, use an isolated unprivileged
builder with no network or credential access; incompatible dependencies are not
installed. The completed slot is immutable/root-owned before activation.

## Durable transaction and boot recovery

Never overwrite the confirmed slot. Keep independent durable records for the
confirmed release and a pending transaction; do not rely on a mutable symlink alone.
States: downloading, preparing, ready, trial, confirmed, rollback, quarantined.

1. Download/prepare candidate; the confirmed release stays bootable.
2. Flush every candidate file and required directory entries before recording ready.
3. Persist trial identity and intended previous/candidate releases, then atomically
   select the candidate. Each record update uses temporary write, fsync, rename and
   parent-directory fsync. Candidate/confirmed paths are validated within slot roots.
4. On every boot, the stable launcher validates records and slots before starting
   the application. Partial preparations are ignored. Missing/inconsistent candidate
   state selects the separately recorded confirmed release, not a guessed path.
5. Run a bounded trial with an independent supervisor: UI heartbeat/render readiness,
   stable services and passive native-library initialization. Internet availability
   and active camera/TV probing are not health criteria. Native call/answer admission
   remains fenced during trial. Crashes, missed heartbeat or startup deadline cause
   rollback. Record each trial attempt before launching; cap interrupted attempts.
6. Flush confirmation before changing the confirmed-release pointer. Boot recovery
   handles interruption between these operations using the transaction identity.
7. Restore the confirmed slot on failure, display rollback progress, then release
   maintenance only when the old app is ready. Quarantine failed versions; do not
   endlessly retry them. Report failure when connectivity returns.

Retain the prior confirmed slot until durable confirmation and retain at least
one recovery slot afterward. Bound disk use and logs; garbage collection never
removes current, confirmed, previous-recovery or in-flight slots. Shared data
formats remain backward compatible throughout the rollback window. Backups do
not make destructive migrations safe for this first implementation.

## Staged delivery

1. Doorstop PROD/TERM/SRV update requirements and reciprocal verification plans;
   pure release/transaction model and deterministic crash-boundary tests.
2. Stable updater, safe staging, signature/compatibility verification and durable
   records; installer provisioning and archive tests remain under tests/adhoc.
3. Boot launcher, independent trial watchdog and rollback; inject failure/power-cut
   boundaries with an emulated filesystem/process harness.
4. Terminal maintenance admission, passive startup and persistent localized display;
   tests cover incoming/outgoing races, settings/setup, all supported language layouts.
5. Server status/admission integration and automatic feed policy, without adding an
   administrator approval requirement.
6. Release workflow machine assets and signing; artifact verification tests and
   backward-compatible distribution/documentation changes.
7. Pi qualification: successful update, invalid/incompatible package, insufficient
   space, interrupted download, failing candidate and power cuts during preparation,
   activation and confirmation. Verify enrollment, settings, pairing, camera sleep,
   TV power/source and no update during calls. Simulated tests are not physical runs.

Each implementation stage uses its own issue/feature branch/PR, Android version
increment, appropriate LLT/HLT plus independent installer checks, and clean Verify
before merge. Update affected technical/user-guide authoring sources and regenerate
derived manuals/bundles. Never publish signing keys, device state or private logs.

## Current status

Implementation through PR #128 is merged: signed release staging, stable root
supervisor, boot recovery, independent localized display, safe app admission,
private data checkpoints, installer bootstrap, server caching/telemetry/admission,
and release publication. Production signing runs only in GitHub Actions.

The server integration is deployed. Term2 runs the independently verified signed
v0.3.71 baseline with updater services active. Actual native preparation and an
isolated native-core startup check passed on the Pi. The current qualification
branch closes passive-sleep and supervisor-fence continuity gaps and strengthens
the native preflight. Code, regression plans and runtime requirements are updated.

See [terminal-update-qualification.md](terminal-update-qualification.md) for executed
checks and remaining automatic-transition/recovery/call scenarios. Physical power
interruption has not been tested. OS/dependency upgrades remain excluded.
