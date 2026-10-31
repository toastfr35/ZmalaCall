# Android app architecture improvement plan

## Objective

Make screen lifecycle, call lifetime and background work easier to reason about
while retaining the focused UI, push-based incoming calls and update continuity.

## Findings

The local Floorplan maps 42 files into screens, calls, photos, alerts and updates.
Java same-package references required supplementary connections; these indicate
source dependencies, not guaranteed runtime invocation. `MainActivity` owns screen
navigation plus configuration fetches, several call fields, ringtone/display
listeners, enrolment and push preparation. `CallSession` already owns the live call,
but retains a weak MainActivity reference and invokes screen methods directly.
Both activity and session retain visibility, output and reconnecting-related state.

## Ordered implementation stages

1. **Define a single owner for live call state.** Inventory fields in MainActivity,
   CallSession and CallEngine. Keep call state, output selection and microphone state
   in the call/session layer; retain only presentation state in the activity.
   Expose a read-only screen snapshot and explicit user actions. Verify recreation,
   background/foreground transitions, audio route cycling and notification answer.
2. **Detach the session from the concrete Activity.** Replace direct MainActivity
   callbacks in `CallSession.java` with a small observer contract and explicit
   attach/detach lifecycle. Retain application-context ownership and main-thread
   native calls. Verify no duplicated callbacks or leaked activity and that a call
   survives screen replacement. Do not move live calls into the screen layer.
3. **Extract setup and contacts coordination.** Move enrolment, permission flow,
   contact/configuration loading and stale-result checks out of MainActivity into
   small owners. Keep ContactScreen and ContactCard concerned with presentation.
   Verify QR scanning/import, denied permissions, invalid setup, server outages,
   contact selection and portrait loading without changes to the user workflow.
4. **Unify notification-to-call handover.** Document ownership across PushService,
   PushMessage, PushAnswer, IncomingCallScreen and CallService. Use an explicit
   call identity and expiry through the entire handover. Preserve Android service
   and full-screen restrictions rather than hiding them behind a generic bus.
   Test duplicate/stale pushes, locked/asleep phone, dismissed notification,
   manual answer, declined calls and process recreation on real devices.
5. **Consolidate request policy, not every HTTP operation.** Compare ServerApi,
   CallPhotoHttp and UpdateHttp. Share only genuinely identical timeout, cancellation
   and bounded-response mechanics. Keep private server authentication separate from
   public GitHub downloads and retain redirect restrictions. Test failed requests,
   stale enrolment generations, oversized photos and interrupted downloads.
6. **Make update and photo operations depend on narrow call state.** Preserve
   UpdateGate's no-install-during-call rule and PhotoShareEpoch's stale-work protection.
   Pass call identity/lifetime explicitly instead of reaching through activity fields.
   Test hangup while a picker is open, stop/start sharing, background transfer and
   an update becoming ready during a call. Keep native media ownership in CallEngine.

## Preserve and defer

Keep the application-owned CallSession, separate foreground CallService, bounded
portrait loading, photo lifecycle guards and update policy helpers. Avoid a Compose
or Kotlin rewrite, dependency-injection framework or replacement calling SDK as
part of this plan. No third-party dependency removal is justified solely by the map.
A future Play Store build is a separate product/distribution change, not this refactor.

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
No runtime implementation or hardware qualification is included in this change.
