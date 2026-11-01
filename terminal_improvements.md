# Terminal architecture improvement plan

## Objective

Reduce implicit shared state and hardware coupling while preserving the simple
four-button experience, reliable calls and current TV behaviour. Splitting files
alone does not achieve this: ownership and dependency direction must improve.

## Findings

The terminal Floorplan covers 112 code files. Its shared UI, call, setup, Pi and
Windows groups are useful, but `common/main.py` combines eight controller mixins
into `Terminal`. Those controllers share many mutable fields. `common/ui/display.py`
also composes views through inheritance. Imports alone understate this coupling.
The map needed explicit Python package-member connections, including lazy media
selection; `linux/media.py` is used and must not be removed as allegedly dead code.

## Ordered implementation stages

1. **Establish the platform boundary.** `common/main.py` directly constructs Linux
   TV, USB-power and fan classes. Introduce a small platform-services factory with
   explicit Pi services and Windows substitutes. Keep construction and shutdown in
   the application root. Preserve lazy loading of platform-native libraries.
   Verify both startup paths, absent hardware and shutdown ordering.
2. **Extract owned controllers gradually.** Start with settings or callback
   handling from `common/settings_control.py`, `common/call_control.py` and
   `common/management.py`. Give each controller its own state and narrow explicit
   collaborators; avoid passing the entire Terminal object. Retain pure model,
   carousel and volume calculations. Only then migrate call coordination and views.
   Verify red/green actions, rapid navigation, cancelled work and saved settings.
3. **Separate server synchronisation from scheduling.** Split polling and network
   work from `ManagementLoop`'s UI dispatch, timers and hardware checks. Replace
   positional message tuples with named result types carrying generation identity.
   Keep all Tk changes on its owner thread. Verify stale results after reset,
   network loss, pending callbacks and timely button/call processing.
4. **Classify configuration changes explicitly.** In
   `common/configuration_control.py`, compute a change description before applying
   UI, permissions, credentials or media changes through their owners. Preserve
   immediate permission revocation and defer disruptive work during calls. Verify
   hourly relay renewal does not wake USB or rebuild media, and failed updates do
   not advance the applied revision.
5. **Give the media adapter resource ownership.** `linux/media.py` currently
   receives and mutates the whole Engine, including plugin and framing fields.
   Introduce an owned adapter with configure, refresh, volume and close operations
   and a narrow native-engine interface. Preserve core-thread rules and native
   callback lifetimes. Verify C10/C20 recovery, audio routing, first video, preview
   proportions and both call directions before removing the old path.
6. **Separate TV policy from transport.** Keep the existing small
   `linux/tv_plugins/api.py` contract. Extract viewing-session and restoration policy
   from `linux/tv_control.py`; keep CEC/network commands and observations in the
   transport/driver layer. Represent unknown state explicitly. Test incoming calls
   from standby and live TV, unanswered calls, retries during ringing, manual
   navigation, inactivity countdown and restoration on term2. Command acceptance
   must never be treated as proof of the displayed input.

## Target ownership

Terminal application owns screen/input, call controller, server synchronisation,
setup controller and platform services. The call controller owns call decisions;
the engine owns native call lifetime; the media adapter owns media resources.
Views consume state and emit user actions rather than modifying every controller.

## Preserve and defer

Keep isolated QR capture, background-to-UI result delivery, pure model logic,
bounded caches and independent voice/ringtone/button levels. Do not replace Tk,
Linphone or the native video pipeline without evidence of a concrete benefit.
Removing third-party packages is not justified by this review alone.

## Delivery and verification

This is a proposed development plan, not a new product requirement or a claim that
changes have been implemented. Preserve current behaviour unless a separate
feature request explicitly changes it. Each numbered stage is a separate issue,
feature branch and PR; merge only after required Verify checks pass. Follow the
repository Android version-bump policy and rebase competing version changes.

Before each stage, identify affected Doorstop HLR/LLR items and existing LLT/HLT
plans from the implementation's `@llr` comments. Keep their references and tests
synchronized as code moves; update the component technical guide in `docs/`.
Run `make requirements` (or `python build_tools/requirements.py`) when traceability
changes. Add regression assertions for the boundary being changed, not tests that
merely mirror a new class structure. Record skipped and hardware checks honestly.
User guides need edits only if user-visible behaviour changes.

Review the diff for unintended behaviour changes, refresh the local Floorplan,
and compare cross-component dependencies before and after. Completion means the
new boundary has an explicit owner, callers no longer reach through it, old paths
are removed, and relevant verification passes. Avoid introducing frameworks,
general-purpose event buses or extra processes just to implement this plan.

## Review basis and limits

Reviewed on 31 October 2026 using the local Floorplan and selected owning source
files. The map is a navigation aid, not proof of runtime behaviour or a security
audit. Maps remain ignored local artifacts; these plans are the durable record.
The original review did not include runtime changes. Subsequent implementation
and verification are recorded below; no hardware qualification is implied.


## Implementation progress

Stage 1 implementation complete: the platform factory selects typed fan, power
and television contracts and lazily constructs remote input, feedback sounds,
pairing/camera status and TV-check transport. Windows substitutes perform no Pi
hardware I/O. Application shutdown still owns resources; partial factory failure
closes already-created services in reverse order. Native media selection remains
lazy and is addressed in stage 5.

Portable verification covers constructor arguments, failed construction, shutdown,
Windows import isolation, input dispatch, setup and settings. Physical startup and
shutdown qualification on term2 is still pending; no hardware pass is claimed.
Stages 2–6 continue below as they are implemented.

Stage 2: callback ownership extracted into `CallbackController`. Request submission,
acknowledgements, poll reconciliation and once-only availability selection use
explicit arguments instead of reaching through Terminal. Remaining call and view
mixins are deliberately retained until their boundaries can be migrated safely.
No user workflow changes; user guides remain accurate.

Stage 3 implementation: background polling now lives in `server_sync.py` and uses
named generation-bearing result types. ManagementLoop keeps UI dispatch and
scheduling; workers receive captured inputs and detached diagnostic snapshots.
The existing stale-enrollment and callback-revision guards remain at dispatch.

Stage 4 implementation: pure configuration and media-snapshot decisions replace
inline classification. Existing UI-thread application, permission revocation,
credential renewal, retry and applied-revision behavior are preserved. Full
terminal LLT run: 569 passed, 11 skipped; hardware qualification is not implied.
