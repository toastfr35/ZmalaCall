# Server architecture improvement plan

## Objective

Clarify configuration ownership, request boundaries and background delivery without
splitting this small Pi server into multiple services or replacing its storage.

## Findings

The local Floorplan maps 81 non-generated code files across administration,
authenticated requests, calls, family records, notifications and persistence.
`main.js` already provides a useful composition root and test injection points.
`Store extends AccountStore` combines persistence, account mutation, derived views,
password ownership, secure-call configuration and other settings. Request handlers
receive a broad collection of collaborators. The current map does not recognise
custom HTTP routing; its zero endpoint count is a scanner limitation.

## Ordered implementation stages

1. **Document and type request dependencies.** Review `http/handler.js` and each
   route module; supply only the services it needs through narrow typed contracts.
   Keep authentication, local-network admin restrictions, body limits and persistence
   failure checks at a common boundary. Create a reviewed route/access inventory
   from code before using map coverage as evidence. Test admin/device separation,
   unknown routes, invalid payloads and denied operations.
2. **Separate state storage from account operations.** Refactor `store.js`,
   `accounts.js` and `contact-directory.js` incrementally toward composition.
   Keep one authoritative state owner and explicit mutation methods, rather than
   handing writable records to more callers. Preserve revision checks and the
   existing persisted format. Test concurrent edits, enrolment identity, contact
   permissions and persistence failures before changing ownership further.
3. **Make durable mutations explicit.** Clarify the contract between SnapshotFile,
   configuration commits and bootstrap publication in `main.js`. An acknowledged
   mutation must have the required durable writes completed. Keep startup migration
   separate from normal request operations. Verify failure ordering, restart,
   restore and dependent bootstrap writes. Do not introduce a database just to
   simplify class names; first establish whether current semantics need one.
4. **Decouple notification delivery from call routing.** `main.js` currently wires
   callbacks to SIP and obtains push delivery through `sipServer.appCalls?.push`,
   then assigns callbacks back onto the SIP server. Inject narrow notification and
   call-status interfaces instead of navigating another service's internals.
   Preserve existing retry and duplicate-suppression behaviour. Test push unavailable,
   SMTP failure, cancelled callbacks and multiple delivery channels independently.
5. **Clarify call and photo lifetimes.** Review `sip-dialogs.js`, `app-calls.js`,
   `call-photo.js` and shutdown ownership. Keep call identity and permission checks
   explicit at photo access boundaries. Avoid duplicating active-call state in more
   services. Verify late messages, cancelled calls, expired photos, concurrent
   sharing attempts and cleanup after disconnect.
6. **Keep admin UI modules feature-owned.** Work on `web/admin-*.js` sources,
   not generated `admin.js` or `admin.css`. Reduce access to global UI state where
   a feature can own its draft and rendering lifecycle. Preserve unsaved edits,
   revision-conflict handling and accessibility. Test account edits, terminal
   settings, setup downloads and navigation before and after extraction.

## Preserve and defer

Keep the composition root, route separation, validation modules, bounded history,
atomic snapshots and dedicated notification helpers. Do not add microservices,
a generic repository framework or a new UI framework for this cleanup.

The map's two high-severity secret warnings refer to `autocomplete` labels
`new-password` and `current-password` in `web/admin-auth.js` and its generated
bundle. They were checked as false positives, not evidence of leaked credentials.
This does not constitute an audit of all authentication or secret handling.

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
