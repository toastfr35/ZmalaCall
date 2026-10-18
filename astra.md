# ZmalaCall implementation and specification review

## Administration interaction and cleanup review — 18 October 2026

- Prevent periodic refreshes from removing a focused account action or view
  control. Account search remains outside the refreshed row region.
- Support credential copying over plain LAN HTTP with a dialog-scoped fallback,
  focus restoration and visible manual-copy guidance if the browser blocks it.
- Clear the console on opening and ignore responses/errors from an earlier
  opening, including closing and reopening the same terminal.
- Remove the unused `presenter-back-power.png` illustration and its obsolete
  notes (about 1.4 MB). The terminal uses `presenter-turn-over.png` and
  `presenter-pairing.png`; runtime and packaging references were checked.
- Remove unused legacy setting-box/toggle/countdown CSS and ignore generated
  browser screenshots. Keep the current guides, CAD sources, diagnostic tools
  and portrait fixtures: these have distinct uses and are not disposable builds.

Verification: 88 server tests, combined lint/type/generated-asset checks, and
47 packaging tests (six platform-dependent skips). Browser checks verified
actual LAN-HTTP copying, keyboard focus across polls, Escape/Enter dialog
navigation, console opening and all six pages at 320/768/1920 CSS pixels.
No horizontal page overflow or clipped panels were found in those 18 checks.

## Responsive administration review — 17 October 2026

Tested all six server pages with disposable accounts in Chromium viewports from
320 to 1920 CSS pixels. Fixed hidden phone navigation, tablet authentication
buttons overlapping content, off-screen account actions, and a clipped terminal
association row at small laptop widths. Phone accounts now stack with column
labels; desktop accounts retain their table. Dialogs fit dynamic viewport height,
long names and credentials wrap, and phone/touch controls have larger targets.
Responsive CSS now loads after component styles.

The final 48 page/viewport checks found no horizontal page overflow, clipped
panels or out-of-bounds controls. Additional checks covered breakpoint edges,
short landscape dialogs, all eight editing/setup/console dialog types, account
search/filtering, group saving and terminal settings surviving reload. There
were no browser console warnings/errors. All 82 server tests and `make lint`
passed. These are browser viewport tests, not physical iOS/Android certification.
The repeatable manual checklist is in `docs/implementation.md`.

## Maintainability and consistency review — 17 October 2026

This pass starts from `01c2ce8`. It covers first-party terminal controllers,
configuration/provisioning, remote/TV/USB adapters, native media boundaries,
server HTTP/SIP/media/persistence, administration modules, installer contracts
and their documentation. It is a code and regression review, not a new
hardware qualification or a formal security audit. Dated findings and measurements
below remain historical evidence; this section records the current changes.

### Refactoring applied

- `main.py` now concentrates on terminal composition and lifetimes. Input
  dispatch lives in `input_control.py`, and configuration/engine application
  in `configuration_control.py`. These controllers share the existing owning
  terminal, avoiding duplicate state or new cross-thread ownership.
- Call actions have separate callback, dial-preflight and USB-ready answer
  functions. Generation/serial guards remain at asynchronous completion points.
- Configuration polls and local-setting responses use one validation/cache
  boundary. Stable snapshots omit volatile presence and callback state.
- Server profile validation moved from the store into pure
  `terminal-settings.js`; the store validates complete candidates before mutation.
  Device read/write responses share the same live-configuration builder.
- Admin terminal fields are split into Calls, Video & audio and General builders
  in `admin-terminalfields.js`. Card selection, association and saving stay in
  `admin-terminals.js`; generated `admin.js` was rebuilt.
- Server shutdown is centralized in `shutdown.js`. Listener failures and process
  signals share one drain/flush operation.

### Defects fixed

| Defect | Correction and regression |
| --- | --- |
| Frame-rate selector existed in the field registry but was never attached to the page | Append it in Video & audio; a tree-fixture test requires every registered control to belong to the visible form |
| Settings responses bypassed configuration rollback protection | Share acceptance policy with polling; reject an older response without replacing the cache |
| Authenticated HTTP could follow redirects with enrollment credentials | Reject redirects; an isolated HTTP fixture verifies no second request is made |
| Retrying an applied setting advanced the revision and wrote another snapshot | Keep the revision for no-op retries while retaining the route's persistence barrier |
| Focus loss could swallow the middle-button release and leave volume motion active | Stop the gesture and invalidate delayed TV visibility results on focus loss |
| HTTP bind failure could leave an optional HTTPS listener serving a partially stopped app | Close both listeners and SIP, drain pending requests and flush once; real socket tests exercise drain ordering and repeated shutdown |

The callback error path also tolerates a missing media engine, allowing offline
callback handling to fail cleanly instead of throwing a second exception.

### Documentation and specification

The README is now an installation/operation/development entry point rather than
a description of one developer PC. Design and implementation docs describe the
current module boundaries, three/five portraits, settings hold, TV idle return,
remote pairing/button verification, battery/charging and configurable video rates.
Pi admin-password recovery now distinguishes the installed service's data path
from the legacy boot-partition path. Installer, automatic-framing and hardware
guides distinguish current defaults from dated observations and future GPIO work.
Admin account help no longer assumes the browser and server run on the same PC.

Doorstop sources were corrected and regenerated, with new traceable records for
remote onboarding/status, TV setup/idle restoration and Pi server deployment.
Requirement review stamps remain a separate maintainer acceptance step; structural
validation does not claim every hardware requirement is qualified.

### Verification in this pass

| Check | Result |
| --- | --- |
| Server suite | 82 passed |
| Terminal suite | 270 run: 267 passed, 3 Linux-only skips on Windows |
| Installer/package suite with installer dependencies | 47 run: 41 passed, 6 platform-dependent skips |
| Real Tk Settings test | 95 languages, six editors, both focus sides at 900×620 and 1280×720; hold, reset navigation and cancellation passed |
| `make lint` | JavaScript, strict type checking, Python, native static analysis, shell/PowerShell syntax, formatting and generated assets passed |
| Doorstop and generated catalogues | Structural validation, publication and generated links/anchors passed |
| Documentation | Edited Markdown file links, UTF-8 and whitespace checks passed |

These checks use isolated fixtures. No Pi deployment, live call, TV wake or server
restart was performed in this pass. The existing unrelated Word-guide edit was
preserved. Native media behavior was not changed; its opening source comment was
corrected to describe the current decoder ownership.

### Remaining work and deliberate limits

1. Keep controller mixins small and state ownership in `Terminal`. A future typed
   host protocol would make their dependencies more explicit; a wholesale
   controller-object rewrite would add churn without addressing a reproduced fault.
2. Native queues and render caches still need byte/frame-age budgets and longer
   soak evidence. Do not drop arbitrary compressed H.264 packets to imitate the
   safe newest-frame policy for independent JPEG/raw frames.
3. Native and QR shutdown can wait on SDK/process operations. Measure worst-case
   recovery before introducing asynchronous teardown or bounded forced termination.
4. Snapshot rename is not fsync durability or a transaction across files. Backup
   restore epochs, data migrations/rollback and concurrent whole-form admin edits
   deserve their own design and fault-injection tests.
5. Retention for portrait/render caches and long-lived diagnostic files remains
   separate from the installed volatile journal and bounded command histories.
6. Real TV/USB/power-loss acceptance and the serial-keypad host adapter remain
   distinct hardware work. Passing portable tests does not qualify another TV,
   a different camera, sustained 30 fps or Internet-facing SIP.

---

Reviewed 10 October 2026 against checkout `e5ece28` and the working files present during review.

Deeper implementation pass: 10 October 2026, checkout `bfd1274` plus the current working files. Findings 5–10 and the optimization analysis below were added in this pass. Tests and probes remained isolated from production state and hardware.

The project has useful separation between terminal state, UI, platform adapters, SIP routing, and persistence. Existing tests cover many difficult cases, including late call cancellation, stale enrollment results, message authentication, and asynchronous media allocation. The highest-priority fixes concern unauthenticated SIP resource growth, remote-command ownership and persistence recovery, and safe recovery when media or native-engine configuration fails.

The findings below preserve the original review evidence. The implementation status added here supersedes their original suggested-fix wording. Existing unrelated working-tree edits were preserved; results describe the files tested, not an immutable release. Hardware risks remain separate from fixture-verified fixes.

## Implementation status — 10 October 2026

Applied the ten reproduced defects and the bounded optimizations below. Added regression tests, updated Doorstop source records and regenerated their Markdown catalogues. See [platform/recovery behavior](docs/reliability.md) for deployment limits and migration details.

| Finding | Applied change | Regression evidence |
| --- | --- | --- |
| 1 — Command ownership | Jobs carry immutable device serials. Replacement devices cannot claim old commands or view old output. Pending legacy jobs without provable ownership are cancelled/lost. | `zmala_server/tests/reliability.test.js`, existing association tests |
| 2 — Output stalls | Bound decoded text to 65,536 combined UTF-8 bytes; allow 400,000-byte JSON bodies. Permanent rejection submits a bounded diagnostic then resumes polling; transient errors retry results without rerunning commands. | NULs, malformed UTF-8, Unicode, permanent and transient failure tests |
| 3 — Persistence recovery | Subsequent barriers retry the latest failed snapshot, including a completed-in-memory result with the same lease. Concurrent duplicates wait for commit. | Repeated injected disk failures, concurrent result retries and reload |
| 4 — Hidden badges | Pruning and saved-count loading use call-permitted contacts; regrant does not resurrect pruned counters. | `zmala_terminal/tests/test_reliability.py` |
| 5 — SIP retention | Strict bounded Content-Length framing and a 30-second unfinished-message deadline. ACK bypasses contexts; other contexts have expiry and per-IP/global quotas. | `zmala_server/tests/sip-bounds.test.js`, existing real-UDP cancellation test |
| 6 — Linux reset | Secret-free Wi-Fi cleanup identifiers survive reset/restart; cleanup retries before new enrollment and tolerates an already-deleted UUID. | Controller failure/restart test; Linux adapter regression has a Linux-only execution gate |
| 7 — Engine recovery | Publish the applied revision after successful engine setup; release failed cores and retry latest desired configuration while idle with five-second backoff. | Injected constructor failure, same-version poll and recovery |
| 8 — Media negotiation | Validate before mutation, stage established-call updates, commit on success, discard on rejection, close disabled streams and reclaim late allocations. Cache rewritten final responses for retransmission. | Media staging/allocation and overlapping/rejected/successful renegotiation tests |
| 9 — Portrait polling | Independent bounded portrait worker validates and atomically replaces images, retries failed paths and cancels stale publication. | Blocked download while config polls finish, partial-cache repair, hash/truncation and cancellation tests |
| 10 — Failure isolation | Device routes await their own mutation. Config reads remain available after console save failure. `/ready` reports known persistence degradation separately from `/health`. | Failed commits 500, config/health 200, readiness 503 then 200 after retry |

**Compatibility choices:** legacy unowned jobs are not rebound to a current username. In-dialog INVITE must carry an SDP offer (488 otherwise); overlapping negotiations receive 491. Snapshot replacement still does not promise fsync or cross-file transactions.

**Optimizations applied:** snapshot coalescing retains at most one active and one latest queued snapshot per file, with acknowledgements waiting for commit (tested with 200 queued revisions). Mixer subprocesses use one worker and coalesce superseded values. Photo conversion admits ten outstanding uploads, runs at most two converters, shares identical in-flight inputs, and checks dimensions before decoding. Linux conversion uses Python/Pillow; Windows uses PowerShell. Synchronous JSON serialization remains a measured optimization opportunity.

**Specification and verification:** corrected platform, LAN administration, output, identity, persistence and reset contracts; documented restore/re-enrollment; added TERM024 for outstanding serial-keypad host integration. Added Linux and Windows CI jobs with Linux process tests, package checks, firmware simulation and Doorstop validation. CI configuration is authored and parses, but has not run on a hosted runner in this session.

**Remaining recommendations:** native byte/frame-age budgets and hardware benchmarks; render-cache byte budgets/incremental carousel rendering; asynchronous QR/native shutdown; cache/log retention policy; cross-file transactions and restore epochs; SIP response-flow and cross-core text-dedup investigations; detached Linux child supervision; release manifests/automated rollback; serial host adapter and physical/usability acceptance. These require additional design or target-hardware evidence and are not represented as completed fixes. Native frame-pipeline changes already present in the working tree are separate work.

### Verification after applying fixes

| Check | Result |
| --- | --- |
| Server suite | 69 passed |
| Terminal suite | 138 run: 135 passed, 3 Linux-only tests skipped on Windows |
| Packaging and Linux portrait converter, using bundled Python with Pillow | 5 passed |
| Keypad firmware freshly compiled with g++ | 56 simulated checks passed |
| `make lint` | Passed JavaScript, TypeScript, Python, native source, shell, PowerShell, formatting and generated-asset checks |
| Doorstop structural validation and catalogue regeneration | Passed; generated links/anchors resolve; review stamps remain unclaimed |
| Live Pi/C20/network/device acceptance | Not run; no live services, enrollment or production accounts modified |

## Reproduced defects

Priorities: **P1** = address before unattended deployment; **P2** = fix in the next reliability pass. Findings below distinguish fixture reproductions, source-level probes, and consequences inferred from the production control flow. No real accounts or calls were used.

### 1. P1 — Old commands can execute on a replacement terminal

**Evidence:** `zmala_server/console-jobs.js`, especially `create()`, `claim()`, and `list()`; `zmala_server/http/admin-routes.js:172`; `zmala_server/accounts.js`, `deleteAccount()` and `makeTerminal()`. Related requirements: SERV002, SERV014, SERV015.

Console records are keyed by the mutable account username (`terminal_id`). Deleting an account removes its credentials and profile but leaves its queued jobs. Creating another terminal with the same username generates a new serial and token, yet `claim()` delivers the old account's commands to it. Existing command output/history is also selected by that reused username.

**Reproduction:** Through the fixture HTTP API, queue `echo prior-device-command` for `term1`, delete `term1`, recreate it as a terminal, and claim work using its new token. The serial changed, but the returned job ID was the old queued job. A command intended for a retired device could therefore execute on a different device. Converting a terminal to a phone and back has the same identity-lifetime concern.

**Suggested fix:** Store command ownership under an immutable device identity or enrollment incarnation. Resolve that identity from the authenticated token when claiming/reporting. Cancel pending work when the corresponding device is retired; retain history under its original identity. Renaming an account must not transfer ownership, and association changes must follow the intended physical serial. Define how legacy username-keyed jobs migrate, conservatively cancelling jobs whose original device cannot be established.

**Regression checks:** Queue and complete jobs, then delete/recreate the username or convert terminal → phone → terminal. The replacement must neither claim old work nor inherit old output. Retain the existing positive test that legitimate reassignment preserves a physical terminal's jobs.

### 2. P1 — Console output limits can permanently stall maintenance polling

**Evidence:** `zmala_terminal/maintenance.py:61`, `:91`, and `MaintenanceAgent.loop()`; `zmala_terminal/configuration.py`, `request()`; `zmala_server/http/device-routes.js:81`; `zmala_server/console-jobs.js:143`. Related requirements: SERV014, TERM021.

The terminal limits retained raw output to 65,536 bytes, but then decodes it with replacement and JSON-encodes it. The server independently limits the HTTP body to 150,000 bytes and decoded UTF-8 output to 70,000 bytes. These are different size measures. Valid retained output can exceed either downstream limit.

**Reproduction:** A result containing 65,536 NUL characters has 65,536 output bytes but a 393,353-byte JavaScript-serialized JSON body including fixture metadata; the API returns HTTP 413. Separately, 65,536 invalid UTF-8 bytes can decode into 196,608 UTF-8 bytes of replacement characters. Python's default JSON escaping can expand the wire representation further.

After a rejected submission, `pending` remains set. Each loop retries the same rejected result before reaching `/api/console/next`. A deterministic 400/413 therefore blocks subsequent jobs for the lifetime of that agent, even after the server marks the old job lost.

**Suggested fix:** Specify a single output contract: either transmit bounded raw bytes using base64, or bound the encoded text while accounting for JSON escaping. Align the HTTP body cap with the maximum permitted representation and metadata. Handle permanent result rejection explicitly: submit a bounded diagnostic result when possible and expose a recoverable failure state. Preserve the rule that commands themselves are never automatically rerun.

**Regression checks:** Run commands producing NULs, non-ASCII text, malformed UTF-8, and mixed stdout/stderr at the limit. Each result must either be accepted or terminate with an explicit bounded error, and the next queued command must run. Also verify retry after a genuinely transient network error.

### 3. P1 — A temporary result-save failure does not recover on retry

**Evidence:** `zmala_server/console-jobs.js:126–157`, `zmala_server/snapshot-file.js`, and the persistence barrier in `zmala_server/http/device-routes.js`. Related requirements: SERV014, SERV015.

`finish()` changes the job to completed in memory before its asynchronous snapshot commits. If the write fails, the HTTP response correctly fails. However, a retry takes the completed-job early return and never queues another write. `SnapshotFile.flush()` continues returning the previous rejected operation, even after the disk becomes writable. The terminal keeps retrying and does not claim new work.

**Reproduction:** Claim a job, inject one rename failure when saving its result, restore normal filesystem behavior, and call `finish()` again with the same lease/result. The domain method returns `{ok: true}`, but `flush()` still fails; persisted status is `running` while memory says `completed`. Recovery currently requires another operation to enqueue a full snapshot, or a restart with loss of the unpersisted result until resubmitted.

**Suggested fix:** Distinguish completed-in-memory from committed completion. An idempotent retry must ensure the existing result is committed before acknowledging it. One option is a dirty revision with an explicit retryable commit operation; another is staging mutations until their write completes. Do not simply swallow the persistence error or resend the command. Review callback receipt persistence for the same memory-versus-disk distinction.

**Regression checks:** Inject a single result-write failure, restore the filesystem, retry the identical result, and assert HTTP 200, persisted completion, and successful claiming of the next job. Restart and verify the output remains present. Also exercise repeated failures and concurrent duplicate result submissions.

### 4. P2 — Revoking contact access leaves an unreachable unread badge

**Evidence:** `zmala_server/store.js`, `buildContacts()`; `zmala_terminal/model.py:59`, `:75`; `zmala_terminal/missed_calls.py:32`. Related requirements: SERV004, TERM012–TERM014.

The server includes all other accounts in configuration, marking non-permitted ones with false permission flags. The carousel filters by `can_call`, but notification pruning and persisted badge loading use every contact ID. Removing the last shared group therefore hides the contact while retaining their count in the corner total. The user cannot open that contact's confirmation to acknowledge it.

**Reproduction:** Give Alice one notification, then refresh configuration with Alice's `can_call` and `can_receive` both false. Only Bob remains in the carousel, while `notifications` still contains `alice: 1` and the total remains one. The same eligibility mismatch exists when restoring saved counts.

**Suggested fix:** Define badge eligibility consistently with accessible contacts. For the current symmetric group model, prune counts when permission is removed, both during configuration updates and on load, then persist the pruned state. If retaining hidden notifications is desired, specify an accessible acknowledgement flow instead.

**Regression checks:** Revoke the last shared group, restart, and confirm the hidden badge does not return. Removing one of several shared groups must preserve the badge while the contact remains permitted. Re-granting access must follow an explicit policy rather than accidentally resurrecting old counts.

### 5. P1 — Unauthenticated SIP input has two unbounded retention paths

**Evidence:** `zmala_server/vendor/sip/sip.js:169`, `makeStreamParser()` at line 441; `zmala_server/vendor/sip/proxy.js`, `contexts`, `onRequest()`, and `start()`; `zmala_server/sip-server.js`, `request()`; `zmala_server/sip-messages.js`, `reply()`.

**TCP body parsing:** `Content-Length` is converted with unary `+`, but is not required to be a finite, nonnegative integer. With `Content-Length: invalid`, the result is `NaN`. Both the maximum-length comparison and the body-completion comparison then stay false. Subsequent chunks accumulate in the body buffer without the header/body flood limits being applied. Authentication and application request validation occur only after parsing completes, so neither protects this path.

**Probe:** Feed the actual exported parser a malformed length, then 1 MiB in 4 KiB chunks, with an explicit 8 KiB body cap. It emits neither a message nor a flood rejection. The same occurs with the literal `NaN`. This was a bounded parser-level probe, not a live denial-of-service test. Source inspection shows why retaining more chunks can continue.

**Proxy context retention:** `onRequest()` creates a process-global context for every routed request, including ACK. Contexts are normally removed when forwarding a final response, but ACK has no response. An ACK for an unknown dialog also reaches the application's deliberately silent ACK rejection. There is no context expiry or capacity limit. Thus normal ACK traffic leaks entries, and arbitrary unique unknown-dialog ACKs can grow the map before authentication.

**Probe:** Evaluate the unchanged proxy module in an isolated VM with a fake SIP transport and an inspection hook, then deliver 10,000 distinct ACKs. All 10,000 contexts remain. Calling its stop hook does not clear them. The production router's silent ACK path was checked separately in source.

**Suggested fix:** Validate framing before entering body accumulation: require a finite, safe, nonnegative integer; reject conflicting/malformed lengths; enforce an accumulated-byte cap and absolute message deadline. Avoid creating proxy contexts for ACK-only forwarding, and give necessary contexts explicit transaction-owned cleanup, expiry, and a global/per-peer capacity limit. Bound this state before application authentication. Keep patch provenance and upstream-diff documentation current.

**Regression checks:** Invalid, negative, fractional, oversized, and conflicting lengths; segmented and pipelined valid messages; unfinished bodies; unknown-dialog ACK bursts; normal successful call ACKs; cleanup after timeout and shutdown. Assert retained state remains bounded without breaking retransmissions or CANCEL handling.

### 6. P1 — Linux factory reset retains the saved Wi-Fi connection

**Evidence:** `zmala_terminal/setup_flow.py:96`; `zmala_terminal/platforms/linux_wifi.py`, `connect_wifi()` and `forget_wifi()`. Related requirement: TERM018.

`factory_reset()` decides whether to run the Wi-Fi deletion worker using only `wifi.get('windows_profile')`. Linux enrollment instead stores `linux_profile` and `linux_uuid`, and creates a persistent NetworkManager connection with autoconnect enabled. Reset clears the enrollment record and proceeds to QR scanning without calling the Linux deletion adapter. The OS connection and its secret remain, while the application loses the UUID needed to remove that connection later.

**Probe:** Exercise the actual reset controller with a Linux enrollment dictionary and mocked OS/UI services. Enrollment reset and scanner startup occur; `forget_wifi()` is called zero times. No NetworkManager operation was performed on this Windows review host.

**Suggested fix:** Delegate ownership detection to the platform adapter, or invoke an idempotent adapter deletion for any saved Wi-Fi enrollment. Retain a deletion tombstone until cleanup succeeds so a temporary NetworkManager failure or restart does not orphan the connection. Continue to leave pre-existing user connections intact.

**Regression checks:** Linux-owned, Windows-owned, and existing-link enrollments; failed deletion followed by restart/retry; no deletion of unrelated connections. A Linux integration test should confirm the owned UUID and its secret are actually absent after reset.

### 7. P1 — Failed engine replacement publishes configuration that was never applied

**Evidence:** `zmala_terminal/main.py`, `apply_config()` at lines 184–227; `zmala_terminal/management.py`, `apply_poll_config()` and `tick()`.

When a SIP credential, video preset, or audio-profile change requires a new core, the model receives the new configuration first. The old engine is closed, then `self.engine = Engine(...)` constructs its replacement. If construction raises, the assignment does not happen: `self.engine` still references the closed old object, with `core=None`, while the model reports the new configuration version.

The next poll sees that version already applied and updates only presence; it does not retry construction. The next tick also attempts to iterate the closed engine before draining queued results. The exact native reaction to a null core was not exercised and must not be assumed safe.

**Probe:** Use the real application/controller methods with a fake engine, accept version 2 with changed credentials, and inject a constructor failure. After another version-2 poll, the published model version is 2, the retained engine's core is `None`, and the constructor has been called only once.

**Suggested fix:** Separate desired configuration from successfully applied runtime configuration. Clear the old engine reference when closing it, maintain a recoverable initialization state, and retry with bounded backoff while keeping UI and message dispatch alive. Advance the applied version only after success. If platform resources prevent creating both cores simultaneously, make the stop/start sequence explicit rather than pretending it is atomic.

**Regression checks:** One failed and one successful construction for the same revision; repeated failures; cancellation/reset during recovery; UI responsiveness; no native call with a null core; correct status reporting of desired versus applied settings.

### 8. P1 — SDP changes mutate live media before negotiation succeeds

**Evidence:** `zmala_server/media.js`, `rewrite()` and the `stream()` packet handler; `zmala_server/sip-server.js`, `forwardDialog()`.

`rewrite()` updates each live leg's peer and RTP/RTCP destinations as it parses the offer. A later invalid media line throws after earlier mutations have already happened. For an in-dialog INVITE, the server returns 488 without restoring the old media state. Even a syntactically valid offer changes the active destinations before the recipient accepts it; a rejected renegotiation therefore has the same rollback concern.

There is also no deactivation of an existing stream when its new media port is zero or its media type/protocol becomes unsupported. Those branches change outgoing SDP only; old socket handlers and targets remain active.

**Probes:** Start with an audio destination of 4000, then rewrite an offer changing it to 6000 followed by an invalid video port. `rewrite()` throws `Invalid media port`, but the audio target remains 6000. Separately, configure both sides, rewrite one side to port zero, and deliver a packet through the actual relay handler using fake sockets: it still forwards to the previous port 4000. No real media or UDP sockets were used.

**Suggested fix:** Parse and validate a candidate description before touching active state. Stage offer/answer media changes, commit them at the appropriate accepted negotiation boundary, and discard them on rejection, cancellation, or timeout. Explicitly deactivate disabled streams and reclaim unnecessary allocations without breaking later re-enablement. Serialize or version concurrent renegotiations so late results cannot overwrite newer state.

**Regression checks:** Invalid second media section, rejected re-INVITE, failed answer rewrite, overlapping updates, port-zero disable/re-enable, unsupported replacement media, and cancellation while allocation is pending. Assert both forwarding destinations and allocated socket counts, not only the rewritten SDP text.

### 9. P2 — Optional photo work blocks presence delivery and can poison the cache

**Evidence:** `zmala_terminal/configuration.py`, `request()` and `fetch()`; `zmala_terminal/management.py`, `poll()`; `zmala_terminal/ui/carousel.py`, `contact_image()`.

**Polling delay:** `fetch()` retrieves a valid configuration but does not return it until it has tried every missing contact photo serially. The worker queues the presence/configuration event only after this returns. Missing photos retry on every poll, including live-only polls. With up to 39 other accounts, 39 four-second photo timeouts can add roughly 156 seconds before an otherwise successful presence response reaches the UI. Contacts become stale after six seconds; status reporting is delayed too.

**Probe:** A valid 39-contact response followed by simulated 20 ms failures for every photo takes about 0.81 seconds per fetch. Two fetches make 78 photo attempts, even though the configuration itself is immediately available. The larger timeout impact is extrapolated from the configured per-request timeout, not measured on a live network.

**Cache integrity:** Any returned bytes are written directly to the final hash-named photo file. There is no image validation, hash verification, explicit oversized-response rejection, or atomic publication. Existence alone prevents another download. A short successful read or interrupted write can leave a permanently unusable portrait; the UI may also read during the write.

**Probe:** Return just the eight-byte PNG signature from the photo request, then fetch configuration twice. The invalid eight-byte file remains cached and the photo is requested only once.

**Suggested fix:** Deliver validated configuration/presence immediately. Move portraits to a separately bounded download queue with retry backoff, cancellation, and a completion event that redraws affected contacts. Enforce a size limit, validate the image and content hash where the naming contract guarantees it, and rename a temporary file only after validation. Evict invalid cached files so they can recover.

**Regression checks:** Presence remains timely with all photos missing or slow; concurrency stays bounded; failed photos back off; truncated/oversized/invalid images never become final cache entries; reset invalidates late downloads; a repaired photo appears without a configuration-version change.

### 10. P1 — A console-only storage failure disables management for unrelated terminals

**Evidence:** `zmala_server/http/device-routes.js:15–16`, its shared `send()` wrapper; `zmala_server/snapshot-file.js`, `flush()`; the equivalent broad barrier in `http/admin-routes.js`.

Every device response waits for both callback and console snapshot writers, including read-only configuration, availability, and status responses. A failed console snapshot leaves the console writer's last promise rejected. Consequently, unrelated management operations fail even after the underlying disk fault has cleared, until another console mutation successfully queues a snapshot. This expands finding 3 from one terminal's result retry to all terminals' control-plane availability.

**Probe:** In an isolated HTTP fixture, inject one console snapshot rename failure for `term1`, then restore normal filesystem behavior. Fetch `/api/config` using a different terminal's valid token: HTTP 500. `/health` still returns HTTP 200. This needs no failure of configuration storage and no actual disk outage.

**Suggested fix:** Await the commit required by the operation being acknowledged, instead of attaching every store's last failure to every response. Preserve the guarantee that command leases/results and callback mutations are durable before success. Pure reads of unrelated valid state should remain available. Add explicit persistence-health diagnostics and a recovery mechanism; do not silently treat an uncommitted mutation as durable.

**Regression checks:** Fail each writer independently and check which routes should remain usable. In particular, a console-only failure must not block a second terminal's configuration or presence. Relevant mutation responses must still fail until their own commit succeeds. Health reporting must distinguish process liveness from degraded persistence.

## Measured and source-supported optimization opportunities

### A. Reduce whole-history serialization on the SIP event loop

`ConsoleJobs.save()` performs `JSON.stringify(this.jobs, null, 2)` synchronously before handing bytes to the asynchronous writer. With the configured 200 completed-history records and 64 KiB output per record, a synthetic snapshot was **13,130,292 bytes**. Seven warmed serialization runs on this Windows host took **13.72–17.41 ms**, with a **14.91 ms median**, excluding disk work, HTTP encoding, and realistic command metadata. This is a microbenchmark, not a Pi measurement or proof of audible call degradation.

Every queue/claim/result mutation rewrites that history. Concurrent mutations also retain separate serialized strings in the pending write queue. Slow storage can therefore turn an asynchronous design into growing queued memory, while JSON encoding still pauses SIP processing.

**Suggested optimization:** Separate job metadata from immutable bounded output blobs, or use a transactional record store. If retaining snapshots, introduce safe revision-aware coalescing and backpressure: a skipped intermediate revision is acceptable only when the later snapshot contains it and its acknowledgement waits for that commit. Removing pretty-printing saves some bytes but does not solve repeated output serialization. Measure event-loop delay, maximum pending snapshot bytes, and mutation latency with realistic retained output and slow disk.

### B. Keep mixer commands and worker shutdown waits off Tk's event loop

`main.py::apply_config()` invokes `engine.apply_speaker_volume()` even when an unrelated configuration edit leaves volume unchanged. On Linux, `platforms/c20_volume.py::apply()` runs `amixer` synchronously with a five-second timeout. During that wait the UI cannot dispatch buttons or iterate Liblinphone. `QRScanner.close()` also waits synchronously for process shutdown, and native core shutdown ultimately depends on worker completion.

**Suggested optimization:** Apply volume only when its desired value changes, and run the external command in a bounded worker with latest-value coalescing and generation checks. Keep native SDK work on its owning thread. Make camera shutdown asynchronous while preserving the rule that the camera is released before starting the call core. Instrument callback/tick duration and worst-case shutdown latency. The five-second mixer stall is a source-derived upper wait, not a live hardware timing result.

### C. Optimize native video by byte budget and frame age

The native implementation already makes good choices: capture has a latest-frame slot, codec work runs off the ticker, queues are bounded by count, and raw display frames can be discarded without arbitrarily dropping encoded reference frames. Preserve those properties.

Remaining opportunities in `media/video/codec.c`, `filters.c`, and `mjpeg-stream.c`:

- Track queued bytes and oldest-frame age alongside counts. Eight 1080p YUV420 output frames alone represent roughly **24.9 MB** of pixel data, before decoder buffers, input frames, or UI assets. Compressed access-unit sizes vary substantially, so a count cap is not a byte cap.
- Explicitly bound accepted decoded dimensions and access-unit size before large allocations. Verify allocation-failure behavior against the linked SDK rather than assuming every allocator returns null or always aborts.
- Measure the full-plane copies in `encode()` and `decode()`. One 1080p YUV420 copy at 15 fps moves about **46.7 MB/s** of pixel payload. Consider shared/refcounted buffers only after proving native ownership, stride compatibility, and reuse timing; a premature zero-copy change could introduce corruption.
- Exercise `pthread_join()` shutdown with stalled devices/drivers and repeated encoder reopen failures. Worker isolation does not by itself bound shutdown. Record reopen counts, frame age, dropped frames, CPU, RSS, and audio continuity under pressure.

These figures are calculations from dimensions and format, not measured resident memory or hardware throughput. The native files were under active modification, and no C/SDK runtime reproduction was performed in this pass.

### D. Budget render caches by bytes and update carousel items incrementally

`RenderCache` bounds entries rather than pixel memory. Both text renderers retain 120 rendered portraits, 200 text images, and source portraits. The current server converter caps uploaded portraits at 480 pixels, so 40 square decoded RGBA sources would contain about **35.2 MiB** of pixels, plus rendered variants and Tk/native overhead. Do not estimate normal uploads using the Linux renderer's larger 1200-pixel fallback ceiling.

Use a pixel/byte budget as well as an entry cap, preserving active image references. Profile resize/language/long-name workloads before reducing limits. Ringing already reuses canvas items; carousel animation still deletes and rebuilds its canvas contents every frame. Reusing the small set of card/image/text items could reduce Tk allocation and repeated shaping, while retaining the existing portrait-size buckets. Compare p95/p99 tick duration and peak RSS on the target Pi rather than optimizing average desktop frame time alone.

### E. Bound expensive administrative work and long-lived disk caches

`PhotoStore.upload()` starts one PowerShell converter per accepted upload with no shared concurrency limit. Each subprocess decodes the source before resizing, so the HTTP compressed-byte limit is not a decoded-memory bound. Content-hash publication deduplicates final files only after conversion. A normal multi-photo upload burst can therefore compete with the server for CPU and memory.

Use a small conversion queue, bound outstanding requests, inspect supported image dimensions where feasible, and deduplicate in-flight identical sources before decoding. Measure conversion concurrency and SIP event-loop delay under the expected admin workload. Add retention for unreferenced server photos, terminal photo caches, and the append-only QR error log. Any cleanup must preserve currently referenced assets and enough diagnostics for recovery.

## Additional failure paths worth targeted integration tests

These are source-supported risks or contract gaps, not additional demonstrated end-to-end defects:

| Path | Why it deserves a test | Recommended check or decision |
| --- | --- | --- |
| SIP response peer binding | The vendored transaction lookup uses method, Call-ID, and Via branch; the retrieved client transaction does not visibly validate the responding transport peer. The pre-transaction application guard covers CANCEL requests only. | Use private UDP/TCP peers to test a response with known matching transaction fields from the wrong flow. This requires knowledge of the transaction fields; do not describe it as a demonstrated blind remote attack. Verify response correlation before updating call/contact/reachability state. |
| Duplicate text after core replacement | `_seen_messages` belongs to `Engine`, is cleared on reconstruction, and uses arbitrary set eviction at 256 IDs. The spec's duplicate suppression has no stated lifetime/window. | Define the replay/deduplication window and sender scope. Test delayed duplicates across media-setting changes and restart; retain bounded identity metadata independently of the native core if required. |
| Server restoration from backup | The terminal rejects any configuration version below its cached version. Restoring older server state with the same device credentials can leave it rejecting valid configuration until revisions catch up or local state is reset. | Add a deliberate restore/epoch protocol or documented re-enrollment recovery. Do not remove rollback protection without defining which server state is authoritative. |
| Standalone Linux maintenance shutdown | `MaintenanceAgent.stop()` signals a daemon thread without joining it. The POSIX adapter kills a process group, whereas the installed service additionally has systemd control-group cleanup. Descendants that create their own session are outside the original process group. | Test immediate desktop shutdown, timeout, background children, and session-detaching children on Linux. Decide whether standalone mode promises the same descendant cleanup as the systemd service and use appropriate supervision. |

## Specification corrections and missing acceptance criteria

Edit the Doorstop YAML records first, regenerate the Markdown catalogues, and review affected links. Structural validation alone does not establish that the requirements reflect the intended product.

| Area | Observed mismatch or gap | Suggested change |
| --- | --- | --- |
| Supported platforms | ZMC001 and TERM001 describe Windows; TERM021 specifies execution as a Windows user. Linux installation, services, media adapters, and shells are implemented. SERV012 lists only PowerShell, pwsh, and cmd despite accepting sh/bash. | Add an explicit server/terminal platform matrix. Define shell choices and service-user behavior per platform, including incompatible-shell handling during enrollment. Distinguish supported configurations from experimental hardware. |
| Administration boundary | SERV001 says administration remains local to the server PC. `docs/admin-authentication.md`, the handler, and tests intentionally permit LAN password setup and remote sessions; HTTPS is optional. | Choose and document one contract. If LAN administration remains intended, update SERV001 and add requirements for initial setup, password reset, session expiry/revocation, origin checks, and HTTP/HTTPS policy. Remote first setup is documented behavior, not a newly discovered authentication bypass. |
| Serial keypad | `keypad/spec.md` explicitly marks terminal integration as unfinished. The Nano protocol and lamp rules exist, but the reviewed terminal has keyboard/presenter input rather than a serial keypad transport. | Track host integration as a distinct delivery item: configured stable port, nonblocking reads, startup delay, heartbeat, connection-generation filtering, lamp snapshots, and focus-independent presses. Link its acceptance checks into the requirements tree. Firmware completion must not imply end-to-end keypad completion. |
| Persistence documentation | `docs/implementation.md:61` says callbacks and console snapshots remain synchronous. `createApplication()` enables asynchronous persistence for both. | Update the guide to describe current write barriers and recovery behavior. State separately what atomic replacement guarantees, what survives an acknowledged write, and what happens after failed writes or power loss. |
| Device lifecycle | Requirements say credentials/settings/jobs follow the physical serial, but retirement, username reuse, enrollment replacement, and crash recovery during reassignment are insufficiently specified. | Add explicit device-lifecycle rules and acceptance scenarios covering findings 1 and 3. Define whether old command history remains accessible and to whom. |
| Output and notification semantics | “64 KiB combined output” does not identify raw bytes, Unicode text, or wire size. “Removed contacts” does not clarify loss of permission versus deletion. | Define these terms in SERV014/TERM021 and TERM014, including permanent submission errors and notification behavior after permission removal. |

Also refresh `docs/README.md` where it says Doorstop cannot detect a version-control working copy; this checkout is a Git repository. Keep machine-specific IPs and sample credentials clearly separated from general installation instructions.

## Further improvements

These are design recommendations or unverified failure risks, not additional reproduced defects.

1. **Make cross-file identity changes recoverable.** Account rename and terminal association update `server.json`, console jobs, callbacks, and bootstrap files through independent writes. Per-file atomic rename and `Promise.all()` do not create a transaction across them. A crash between commits could leave credentials associated with one identity and jobs/history with another. Prefer immutable account/device IDs plus a small transactional store, or introduce a journal and deterministic startup reconciliation. Test interruption after each write boundary, including reassignment with queued commands.

2. **Define the next deployment's trust boundary.** The current prototype explicitly uses HTTP device management and unencrypted SIP/RTP. Preserve that scope distinction instead of claiming it already provides secure remote deployment. Before extending beyond a trusted LAN, define authenticated encrypted management, certificate provisioning, enrollment-token rotation/revocation, and media/signalling protection. Because administration can queue shell commands, consider a locally issued one-time setup secret while retaining remote browser setup. This would be a deliberate product-policy change.

3. **Add call and hardware recovery acceptance tests.** Existing cancellation and media-allocation tests are valuable, but live reliability also needs phone power loss during a call, network loss/recovery, camera unplug/replug, audio-device disappearance, and repeated Pi calls after idle. Specify how an abandoned connected dialog is cleared: the current server can retain it until its four-hour signalling inactivity timeout, blocking new calls for those accounts. Choose recovery timing and endpoint-visible behavior before changing the timer. Measure call success, audio continuity, frame rate, CPU/temperature, and resource growth on the actual supported hardware.

4. **Improve deployment recovery.** The Linux installer creates separate release directories and selects a current symlink, providing a useful basis for rollback. Add a release identifier/manifest, post-start health verification, a documented rollback command, and a tested backup/restore procedure for persistent state and credentials. Verify interrupted upgrades preserve enrollment and never package runtime data. Distinguish “service process running” from “registered and capable of a call.”

5. **Make verification reproducible and platform-specific.** Add CI jobs for the existing lint/type/server/model checks, Linux adapter tests on Linux, package-content checks, Doorstop validation, and the simulated keypad firmware tests. The default `make test` currently omits the separate packaging tests and keypad simulation. Keep native SDK, UI, electrical, and actual-device acceptance as clearly identified additional gates. Record skip reasons and link requirement IDs to the relevant tests; a file reference alone is not test evidence.

6. **Validate usability with intended users.** The four-button model and distinct confirmation states are a good foundation. Test real button force/spacing, readable names and captions at TV distance, color-independent recognition, auto-answer countdown comprehension, and RTL/long-label layouts on the deployed display. Define measurable acceptance criteria and capture failures before adding more UI states.

## Verification performed in the initial pass

| Check | Result |
| --- | --- |
| `node --test tests/*.test.js` from `zmala_server/` | 57 passed |
| `.venv/Scripts/python.exe -m unittest discover -s zmala_terminal/tests -p 'test_*.py'` | 138 run, successful, 4 skipped |
| `.venv/Scripts/python.exe -m unittest discover -s build_tools/tests -p 'test_*.py'` | 4 passed |
| `npm.cmd run typecheck` | Passed for server and admin source |
| `node build_tools/build-admin.cjs --check` | Passed |
| `C:/msys64/usr/bin/make.exe lint` | Passed, including JavaScript/Python/native checks, shell/PowerShell syntax, formatting, types, and generated assets |
| `build_tools/doorstop.cmd --no-reformat --error-all --no-review-check` | Passed structural validation; reviewed stamps were deliberately not checked |
| Isolated supplementary probes | Reproduced all four defects above; probes were executed from stdin, not added as permanent tests |

## Verification performed in the deeper pass

The server suite was rerun directly with Node, avoiding the npm pretest asset-generation step. Terminal tests were rerun against the updated checkout; the changed total reflects intervening repository changes, not a removal of tests by this review.

| Check | Result |
| --- | --- |
| `node --test tests/*.test.js` from `zmala_server/` | 57 passed |
| `.venv/Scripts/python.exe -m unittest discover -s zmala_terminal/tests -p 'test_*.py'` | 130 run, successful, 3 skipped |
| SIP parser probe | Malformed lengths retained 1 MiB without rejection despite an 8 KiB configured body cap |
| Proxy VM probe | 10,000 unique ACKs retained 10,000 contexts; stop did not clear them |
| Linux reset controller probe | Saved Linux enrollment cleared; deletion adapter called zero times |
| Engine replacement failure probe | New revision published, closed core retained, same-revision poll did not retry construction |
| SDP probes with fake sockets | Invalid offer changed live target; disabled stream still forwarded to old target |
| Photo probes | 78 attempts across two 39-contact polls; invalid eight-byte PNG cached without retry |
| Cross-terminal persistence probe | Console-only failure caused another terminal's `/api/config` to return 500 while `/health` returned 200 |
| Console serialization microbenchmark | 200 synthetic records, 13.13 MB snapshot, 14.91 ms median synchronous encoding across seven warmed runs |

Supplementary probes ran from stdin with mocks, temporary fixture state, or an isolated VM; they were not added as permanent tests. The SIP memory probes did not send flood traffic. The earlier lint/type/Doorstop results remain historical evidence from the initial pass and were not rerun in this documentation-only update.

Neither pass performed live phone/Pi calls, a native UI walkthrough, serial hardware tests, electrical verification, or installer execution. No real contacts were messaged or emailed. Test success does not establish those hardware or deployment properties.

## Suggested implementation order

1. Bound SIP parsing and proxy-context lifetimes before authentication (finding 5).
2. Bind maintenance work to immutable device ownership; repair result limits, persistence retries, and unrelated-store failure coupling (findings 1–3 and 10).
3. Make SDP changes transactional and engine replacement recoverable (findings 7–8).
4. Fix Linux reset cleanup, photo/presence separation, and inaccessible notifications (findings 4, 6, and 9).
5. Add the corresponding regression tests, then profile serialization, UI stalls, native frame age, and memory on the deployment hardware. Use the measurements to choose optimizations rather than making simultaneous architectural changes.
6. Reconcile requirements, complete serial keypad integration, and run hardware, interruption, upgrade, and usability acceptance checks before unattended deployment.

## Live hardware follow-up — 2026-10-10

Tested the Windows term1 (C930e camera, Logi USB headset) against term2 on the Pi 3B (C20 camera/audio), using their configured 720p/15 fps profiles. Measurements are from real UI calls and native media statistics, not simulated SIP success. The Pi and running server still use older code than the complete review-fix commit; these results are not an acceptance test of a fully upgraded deployment.

- **Wi-Fi power saving: useful setting, not a complete fix.** With Pi power saving enabled, the first call's settled receive frame rate ranged from 0 to 16.37 fps, with video round-trip measurements reaching 11.99 seconds; a concurrent ping reached 1.45 seconds. With power saving disabled, the next 20-second call maintained 14.15–15.90 received fps and 14.84–15.19 sent fps after five startup samples, with video round trips of 8.7–42.7 ms. Both directions reported 1280×720. However, post-reboot calls later stalled again with power saving still disabled, so that single favorable result does not establish a resolved network or camera problem. Saved `802-11-wireless.powersave=2` in this Pi's active connection profile and applied it immediately without reconnecting. New application-owned Linux enrollments now request the same setting; existing profiles retain their settings. Real GLib serialization of the enrollment payload was checked on the Pi without creating a connection. See `docs/reliability.md` for existing-profile setup and rollback.
- **Windows native audio startup/shutdown: unresolved.** Repeated outgoing calls took about 41 seconds to reach the UI's connected state. Native traces place 10 seconds in ringback output initialization and about 20 seconds in call output initialization for the Logi USB headset. Incoming calls show the same slow audio-output startup; hangup also blocks in native media teardown. These operations run inside the UI thread's Liblinphone calls, so timers and input handling are delayed. The burst of unknown-payload video warnings occurs while media startup is blocked; subsequent video decoding succeeds, so those warnings alone do not establish an SDP mapping bug. Investigate the Windows audio driver/SDK path and test another physical output before choosing a backend change. Do not mark a SIP-connected call successful until decoded media has settled.
- **Ringtone: confirmed by the user.** Replaced the subtle original chime with a synthesized classic Nokia-style melody, deployed it on both terminals, and verified C20 playback. Conversation volume is unchanged.
- **Pi-originated calls and recovery.** A longer reverse call received decoded 1280×720 video on the Pi, settling at 14.57–15.23 fps after the delayed first frames. The Pi returned to idle after hangup, and its normal systemd service was restored. The Pi reported 47.2°C and no throttling flags during the follow-up. This establishes the PC-to-Pi receive path; Pi transmit frame counters alone do not establish that its outgoing frames reached the PC during that reverse call.
- **C20 capture failure on repeat calls: unresolved hardware/driver recovery.** The final PC-originated call received no decoded Pi video, despite low network latency and a running Pi service. Outside the application, a bounded `v4l2-ctl` capture also produced no frames and timed out (exit 124); a device-level USB reset did not recover capture. Kernel logs include a C20 disconnect and UVC/USB errors during the test session. Cycling the identified C20 hub port left it powered but without a re-enumerated device, including after a kernel port disable/enable. After the user physically reconnected the C20, it still did not enumerate; rebooting the Pi restored `/dev/video0`, and a direct 30-frame 1280×720 MJPEG capture completed successfully at about 26 fps. A brief undervoltage warning occurred before this reboot, but it does not establish the cause of the earlier capture failure; the rebooted Pi reported no throttling flags. Wi-Fi power saving remained disabled after reboot. Do not infer camera health from process liveness, the configured 15 fps value, or small RTCP traffic. Add a capture-stall diagnostic and verify repeated-call/USB recovery before unattended deployment; do not blindly reset shared USB hubs from the application.
- **Acceptance limits.** Network/media counters establish traffic and decoded video, not intelligible speech or visible placement of the local preview. Subjective audio, local-preview placement, unplug/replug, network interruption, long idle and soak tests remain separate gates. The initial 20-second Pi-originated fixture ended before Windows finished its slow media startup and was extended accordingly.

After the physical reconnect and reboot, two consecutive PC-originated calls reproduced the failure: the first received video with stalls; the second recorded zero decoded Pi-video samples throughout 40 seconds of connected time, while PC transmission remained near 15 fps. Both returned to idle. At the second call's startup, the Pi kernel logged UVC probe-control timeouts (`-110`) and an audio endpoint rate-setting failure. A direct capture after hangup failed at `VIDIOC_STREAMON` with an input/output error. Short ping samples during the failed call were 5.7–8.4 ms, although the longer concurrent ping run also showed later multi-second spikes. This establishes a USB/capture failure independent of video decoding; the exact cause, including possible interaction with audio startup, remains unresolved. No automatic hub-reset workaround was added. The Pi was rebooted again for recovery.

**Minimal repeat-capture reproduction after another reboot:** with the app idle and no call running, execute `v4l2-ctl -d /dev/video0 --set-fmt-video=width=1280,height=720,pixelformat=MJPG --stream-mmap --stream-count=30 --stream-to=/dev/null` twice, each under a 10-second subprocess timeout. The first invocation delivered all 30 frames (about 26.16 fps); the second timed out without completing. This reproduces the failure without Liblinphone's call/media graph or concurrent call audio. Investigate the C20 firmware, USB connection/power and the Pi's UVC/USB driver on kernel `6.18.50+rpt-rpi-v8`; the present evidence does not distinguish those causes. A final reboot restored enumeration and the normal idle service; repeated-call acceptance remains failed.

Raw development measurements remain in ignored `build_tools/tmp/live-astra/` files. Native trace logs may contain signalling details and must not be published as general test artifacts.

## Local camera preview and post-reboot follow-up — 2026-10-10

Fixed the missing local-camera inset with a dedicated native rendering surface in the bottom-right fifth of the call view. The MSOGL renderer in the deployed SDK versions discards the legacy composited self-view input, so enabling `core_enable_self_view` alone did not display it. The engine now keeps separate native contexts alive for incoming video and the local preview, using the existing outgoing camera stream. The inset is shown only during calls; idle camera preview remains disabled. Missing-remote-video notices leave the inset visible.

Deployed the preview changes to Windows term1 and Pi term2. Pi screenshots show the local camera inset, and the user confirmed it on term1. Validation: 140 terminal tests succeeded (three skips), the call-feedback UI fixture passed all 95 languages, and full lint passed. Tests cover distinct persistent native contexts, headless configuration, inset placement and hiding after hangup.

After the Windows reboot, one call still received no decoded Pi video: the Pi's local inset was visible while its encoder reported `Invalid argument`. This distinguishes that occurrence from a missing camera image. Its microphone capture pointer also stopped advancing. Rebooting the Pi restored capture for the next test: 38 of 39 samples received video, the microphone capture pointer advanced, and term1's incoming audio level varied from approximately -43 to -24 dBm. Both test calls ended cleanly; the normal terminal applications were restored. Multi-second jitter measurements still occurred, so repeated-call and network reliability remain unresolved. The restarted Windows server now runs the current checkout; the Pi still has targeted patches over its older deployment.

**Audio listening remains unconfirmed.** The user initially reported no sound at term1, then noted that it may have been working; nobody was near term2's microphone during that listening check. Received audio traffic and varying decoded levels establish activity, but do not prove intelligible speech or correct physical speaker output. A call with a known audible source at term2 is still needed before marking this resolved. No speculative audio change was applied.

**Outgoing ringback recovered after restarting term1.** Its post-reboot startup log reported that the configured Logi USB headset microphone and speaker were unavailable. A later fresh engine enumerated both devices with their original names and selected the headset for playback and ringing. The user clearly heard the SDK ringback file in an isolated local preview, then clearly heard ringback in a fresh outgoing call to term2; that call was cancelled before answer and returned to idle. The normal Windows terminal was restarted successfully. This points to retained fallback routing after the headset became available, rather than a missing ringback asset. The SDK device setters can return success after falling back, and current application settings are reapplied only when configuration changes. Add and verify idle-time restoration of the explicitly selected device after reconnection; restarting is a recovery, not proof of automatic hotplug handling. This test did not establish two-way speech.

**Missing term2 audio and video reproduced together in the next user call.** During the call beginning around 13:59 BST, the Pi displayed term1's camera while its local inset was black. The C20 microphone was marked RUNNING at 16 kHz stereo, but its hardware pointer remained zero across multiple reads. With the terminal service stopped, a direct 640×480 MJPEG capture timed out after eight seconds without frames; a three-second ALSA microphone capture returned an input/output error with zero bytes. Resetting only the identified C20 USB device (`0525:a4ad`) completed and re-enumerated its interfaces, but both direct probes failed again. These failures occur before encoding, network transport or Windows playback. The Pi reported no throttling and zero accumulated USB runtime-suspend time, so neither thermal throttling nor an actual autosuspend transition explains this occurrence. A Pi reboot was initiated for recovery; the underlying camera/USB host/driver failure remains unresolved. No shared-hub reset or unverified persistent driver setting was applied.

**360p follow-up required.** The Windows SDK logged that 640×360 was not a supported video definition when applying the new preset. The deprecated size setter therefore cannot be assumed to honor that preset; validate an explicit `LinphoneVideoDefinition` and the actual negotiated dimensions on both platforms. The stalled Pi capture above reported 640×480. This is a separate configuration defect, not an explanation for the direct microphone input/output failure.

Following the recovery reboot, the normal Pi service restarted and a fresh user call showed the C20 picture in its local inset again. The microphone hardware pointer advanced from 592,672 to 1,258,528 samples between checks. That verifies resumed local capture; confirmation of remote moving video and intelligible audio remained pending at the time of this entry. The user call was left running.

## Video quality and spontaneous USB disconnect follow-up — 2026-10-10

The user subsequently confirmed live video and good audio after the recovery reboot above. Quality then became blocky/blurry, followed by loss of both C20 audio and video. That confirmation supersedes the earlier pending listening check, but does not establish sustained reliability.

**Applied configuration and packet-recovery fixes.** Native probes on Windows SDK 5.4 and Pi SDK 5.3 showed that both size setters reject 640×360, including an explicit video definition. An ignored request can retain the previous 1280×720 preference. With the user's agreement, replaced the low preset with supported 640×480 at 15 fps, retaining its 700/1000 kbps upload/download limits. Server migration converts existing 360p profiles once and increments the configuration revision; terminals also translate old cached 360p settings during rolling upgrades. The engine reads back the SDK preference and rejects silently ignored sizes. Enabled the SDK's previously disabled RTCP NACK video retransmission for packet recovery, and exposed sender/receiver loss measurements. This cannot repair a stalled capture device; its visual benefit still needs a stable comparative call.

Validation: 142 terminal tests succeeded (three skips), 70 server tests passed, full lint and Doorstop structural validation passed. An opt-in native probe verified legacy 360p mapping, 480p, 720p and 1080p dimensions and enabled NACK on both installed SDKs. Updated server/admin and specification documents. Deployed targeted terminal patches to the Pi and restarted the Windows server with the migration; the Pi still carries these patches over its older deployment.

**Autonomous call failed sustained-media acceptance.** A 90-second connected test initially delivered 640×480 video at roughly 13–15 received fps after startup, with video round trips of 11–71 ms. Only 13 of the 90 samples reported active decoded remote video; the last active sample was around 14 seconds. Incoming audio/video subsequently fell to approximately RTCP-only traffic. At 14:19 BST the kernel logged the C20 disconnecting and re-enumerating, with USB submission errors reporting no device. The user confirmed nobody touched or unplugged it. The fixture ended the call and returned home; this was not a successful 90-second media test.

During the call, sampled CPU idle was 74–86%, temperature was 51.5°C, and throttling flags were zero. These measurements do not show CPU exhaustion. Wi-Fi transmit rate also fell from 72.2 to 5.5 Mb/s with failed transmissions, despite power saving remaining disabled; network variability remains a separate quality concern. Reported RTCP loss was zero during the short working interval, which does not rule out bursts or establish that retransmission improved quality.

Next isolate C20 USB power, cable, firmware and host/driver behavior before attributing this failure to insufficient CPU. A separately powered USB hub is a useful controlled test, not a confirmed fix: connect only the C20 through it, keep the Pi on its own supply, and repeat bounded calls and direct capture while checking for USB disconnects. The Pi 3B's total USB peripheral budget is 1.2 A; use a compliant hub that does not back-power the host ([Raspberry Pi power documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#power-supply)). The absence of Pi undervoltage flags alone does not establish power quality at the camera. Test wired networking separately once capture is stable. Both normal terminal applications were restored; C20 enumeration and service liveness were verified, but renewed capture has not been established after this latest spontaneous disconnect.

## Further capture and encoder isolation — 2026-10-10

Continued autonomous testing while the user arranges a powered USB hub. Stopping the Pi terminal after the spontaneous USB re-enumeration allowed three consecutive direct 640×480 MJPEG captures (60 frames each, roughly 25–26 fps) and three three-second microphone captures (192,000 bytes each) to complete without another reboot. A concurrent camera/microphone test also completed: 600 video frames and 20 seconds of microphone capture. These checks establish intermittent recovery, not reliable full-duplex calls or intelligible sound; the separate microphone recordings were nearly silent and their raw content was not retained.

A subsequent 60-second PC-originated call lost active decoded Pi video after about 48 seconds, with repeated encoder `Invalid argument` errors beginning around 45 seconds and no new kernel USB disconnect. Incoming audio traffic continued. Temporary encoder diagnostics were then installed. The next 75-second call and a three-minute repeat maintained decoded Pi video after startup, with 74/75 and 178/179 active samples respectively. The three-minute call received roughly 10.9–16.5 fps after five startup seconds. RTCP reported intermittent loss, including PC-to-Pi video loss up to 31.6% in individual reports; these are interval maxima, not whole-call averages. Pi CPU idle samples were 72–77%, temperature 55.8°C and throttling flags zero. Each call ended automatically and returned home.

**Reproduced and fixed a separate encoder size mismatch.** In the next Pi-originated call, diagnostic logs showed incoming raw pictures at 640×480 but an encoder target of 320×240. Each frame returned `EINVAL`, closing and reopening the encoder indefinitely. Added a cached SDK scaler owned by the codec worker: mismatched pictures are resized to the configured target, while matching pictures retain their direct-copy path. Context teardown frees the scaler; source-size changes refresh it. This avoids forcing the encoder back to a larger resolution or changing the user's configured preset. The diagnostics were removed when deploying the fix.

Added an opt-in native hardware regression using synthetic pictures, with actual H.264 decoding and target-dimension checks. It covers equal sizes, target-only changes, source-only changes and restoration to VGA. The original implementation decoded zero frames in both mismatch phases and failed. The fixed implementation decoded 29, 29, 30 and 29 frames in the four phases without encoder errors. Full lint passed, and native compilation used `-Wall -Wextra -Werror`. This establishes the encoder fix independently of the USB camera.

The immediate real-call retest after deployment still sent almost no Pi media: its C20 microphone hardware pointer stayed at zero, and the user confirmed no incoming Pi video or audio. Ended that call and rebooted the Pi. The resize fix does not resolve capture stalls; do not treat the isolated codec regression as a passing end-to-end call.

**Recovery-call result:** the fresh 90-second call after reboot maintained decoded Pi video after startup (89/90 active samples), at 11.4–16.1 received fps and 16–129 ms video round-trip measurements. Pi microphone capture advanced, Windows received audio traffic throughout, and decoded playback levels varied from approximately -43 to -8 dBm. No encoder errors or new USB disconnects were logged during this call. Physical listening was not independently confirmed in this run. PC-to-Pi RTCP loss reports still contained large spikes, so network quality remains unresolved even when Pi-to-PC media is continuous.

**Full-duplex USB isolation result:** with the terminal stopped, concurrent direct microphone recording at 16 kHz stereo, silent speaker playback at 48 kHz stereo, and 640×480 MJPEG capture all completed. Microphone capture returned 960,000 bytes over 15 seconds; playback completed its 15-second interval; video delivered 450 frames at about 25 fps. This short check did not reproduce the failure and does not rule out intermittent power/USB/firmware problems or load from audible speaker output. Both normal applications were restored afterwards. The powered-hub comparison and repeated-call capture reliability remain open.

## Carousel usability follow-up — 2026-10-10

Slowed navigation from 280 to 550 ms and replaced the abrupt ease-out with smooth acceleration/deceleration. Profiling on the Pi 3B showed that timing alone was insufficient: portraits and changing text widths consumed most frame time. Moving cards now reuse fixed-width shaped labels and faster portrait resampling; Linux uses bounded 460 px RGB previews while retaining full-quality settled portraits. Replacement canvas items are created before old ones are deleted so Tk keeps its fonts alive. The animation timer now includes rendering in its frame budget and still yields to input events.

With the real contact photos and a quiet media-engine fixture, the same 1100×800 Pi benchmark improved from two frames per transition (143–228 ms mean draw time) to 13–16 warmed frames (29–37 ms mean draw time). At 1920×1080 with five visible cards, warmed transitions produced 8–10 frames (52–62 ms mean draw time). Cold transitions remain slower (about 0.7 seconds); full-HD Pi rendering still has room for improvement, particularly canvas/image reuse. These measurements include profiling overhead and do not establish frame rate during a live call.

Validation: 138 terminal tests succeeded (three platform skips), all 95 languages passed the six-state Windows UI fixture including ringing, navigation and calling during motion, and full lint passed. Added a stale-canvas-item check and removed a rendering-speed dependency from the ringing-animation fixture. Applied the carousel changes to both test terminals; the Pi received only the relevant timer patch in its older management module.

## Presenter Teams button follow-up — 2026-10-10

Live input capture on term2 showed Teams sending eight-byte vendor HID reports `04 3e 01 00 00 00 00 00` (press) and `04 3e 00 00 00 00 00 00` (release), without the `BTN_0` events expected by the adapter. Added that measured report as red; Mute remains green (`04/3f`). When raw HID is open it is authoritative for call buttons, preventing duplicate actions if Linux also emits `BTN_0`; evdev remains a fallback when raw HID cannot be opened. Pointer, motion, malformed reports and repeat values remain ignored.

Deployed to the Pi and observed red press/release entries in the running terminal log. The user confirmed that Teams cancels the call-confirmation screen back to the carousel. Validation: five focused presenter tests passed, all 139 terminal tests succeeded (three platform skips), and Python lint passed.

## Pi 4 migration — 2026-10-11

The migrated card boots Raspberry Pi 4 Model B Rev 1.5 with Debian 13 ARM64,
kernel 6.18.50 and Liblinphone 5.3.105. The existing KMS/V3D graphics stack and
`bcm2835-codec-encode` backend load successfully. No replacement media backend
was needed. The synthetic resize regression decoded 29/29/30/29 frames across
its four phases, and direct concurrent C20 capture/silent playback completed:
450 VGA MJPEG frames, 960,000 microphone bytes and 15 seconds of playback.

Adapted HDMI-CEC for the Pi 4's two connectors. Selection reads the kernel's
CEC-to-DRM mapping instead of assuming adapter/card numbers match, retains an
already connected adapter, and follows a newly connected port while idle.
The observer resets its routing cache when switching; explicit adapter choices
and outstanding TV-restoration state remain fixed. Verified the native ioctl
on both real Pi adapters and regression-tested differing DRM card numbers,
second-port selection, hotplug, unsupported mapping and restoration safety.
Deployed only the three platform modules over the Pi's existing release.

The original supply produced current undervoltage/frequency-cap flags
(`0x50005`) and repeated kernel warnings. The first call was interrupted for
the user's PSU replacement and is not a completed acceptance test. After the
replacement, autonomous 90- and 45-second calls completed and returned home.
Decoded Pi video was active in 86/90 and 41/45 one-second samples, with the
inactive samples at startup. Received audio continued, with decoded playback
levels of roughly -43 to -9 dBm in the first call. No new undervoltage or USB
disconnect was logged; throttling remained zero. These are short continuity
checks, not proof of long-term stability or physical audio quality. The Windows
SDK reported implausible received frame rates up to 100 fps, so those figures
are excluded from performance claims.

HDMI picture confirmed by the user's TV photo: both connectors initially reported disconnected
and supplied zero EDID bytes, despite Xorg and the terminal running. The new
PSU did not restore detection. A temporary runtime-only forced HDMI0 signal at
1280×720/60 Hz was accepted by Xorg, but the user still saw no picture. The same
signal was then mirrored to both ports; kernel scanout and a captured desktop
showed the terminal correctly rendered at 720p, without a confirmed TV picture.
After reverting those runtime overrides, a boot-time test added
`video=HDMI-A-1:640x480@60D video=HDMI-A-2:640x480@60D` to the single line in
`/boot/firmware/cmdline.txt` and rebooted. The TV then supplied 256 bytes of EDID
on HDMI0, Xorg selected its existing 720p preference, and the user confirmed
the physical terminal picture. This establishes a successful boot-time test;
it does not isolate why detection was previously absent.

Removed the unused second output and saved the final single-port setting
`video=HDMI-A-1:1280x720@60D`. The live display is 1280×720 at 60 Hz with no
obvious clipping in the user's photo. The original boot file is backed up as
`/boot/firmware/cmdline.txt.before-zmala-display-test`. The simplified final
boot setting has not yet had another reboot test. Physical CEC wake/restoration
and sustained media tests with the TV connected remain open.

Validation: 144 terminal tests completed (three platform skips), full lint
passed, and the final focused Python lint and whitespace checks passed.
Existing native frame-rate and camera-fixture working-tree edits remain
separate from this migration change.

**Presenter recovery:** Bluetooth on the new board was software-blocked, and
the SD card retained pairing state for the old Pi 3 controller. Unblocked the
radio, enabled it and paired the Presenter with the Pi 4 using a persistent
Bluetooth agent. Verified bonded/trusted/connected status, correct input-group
permissions and the running terminal's open HID descriptor. Discovery stopped
after pairing. The user confirmed Next/Back, Mute and Teams all work. No
terminal restart or button-mapping change was needed.

## Carousel presentation follow-up — 2026-10-11

The user reported partial-screen artefacts during carousel movement on the
Pi 4. Tk's canvas already double-buffers its redraws, but the kiosk ran bare
Xorg/Openbox without synchronized compositing. Added a separate supervised
Picom service using XRender and VSync, with fullscreen unredirection, shadows
and fades disabled. The GLX backend failed to initialize on the installed Pi
graphics stack; XRender starts successfully using the available Present/Sync
extensions. The installer includes Picom, its explicit configuration and service;
the display starts/stops/restarts it, while a compositor failure does not stop
the terminal. No additional application framebuffer or carousel timing change
was introduced. Physical confirmation that the artefacts are gone is pending.

Deployed the service on term2 without restarting the terminal. Picom used about
5.8 MB RSS and negligible CPU while idle; a short call sample used approximately
1.8% of one CPU core. Autonomous 45- and 60-second calls returned home with
44/45 and 59/60 active incoming Pi-video samples, respectively, at roughly
14–16 received fps after startup and continued incoming audio traffic. The Pi
local preview remained visible. Its remote-video screenshot was black with
compositing both enabled and disabled, so remote-picture acceptance is not
claimed by these checks. No undervoltage appeared. Four packaging tests, full
lint, whitespace checks and on-device systemd unit verification passed.

### Remaining tearing and animation cadence — 2026-10-11

The user reported improvement with compositing but persistent horizontal
breaks. Full-screen repainting plus an X Sync fence did not help, and those
experimental settings were reverted. An X Present event probe measured 468
copy completions and zero flips; Xorg logged `Present-flip: Import BO failed:
Invalid argument`. VSync being enabled was therefore insufficient evidence
of tear-free presentation. The installed Xorg 21.1 driver does not support
the newer TearFree option, and Picom's GLX/EGL backends cannot initialize
with this board's supported OpenGL/GLSL versions.

Selected Raspberry Pi OS's `msdri3` acceleration path instead of Glamor.
The same probe then measured 481 flips and zero copies; another probe with
the original damage-tracking configuration measured 489 flips and zero
copies. The user confirmed that tearing disappeared. Saved the override in
`/etc/X11/xorg.conf.d/21-zmalacall-pi4.conf`; installation is restricted to
Pi 4 boards whose modesetting driver contains `msdri3`. X11 drawing now uses
software rendering, while native video can still use DRI3. HDMI remains
1280×720 at 60 Hz.

The user still found the animation uneven. Its old 20 ms timer budget produced
a median 21.39 ms interval on the Pi, mismatching the 60 Hz refresh. Changed
motion scheduling to absolute 60 Hz deadlines, skipping missed deadlines
instead of accumulating rendering/timer overhead. An 18-second carousel
profile improved median frame spacing to 16.79 ms and measured 450 animated
frames versus 392 before. Expensive uncached frames can still miss a refresh
(the new 95th-percentile interval was 32.65 ms); this is not a guaranteed
60 fps claim. The user confirmed that it is now smooth enough. Normal idle
and call polling keep their existing 20 ms timer.

The live Pi is an older release, so only the scheduling change was applied
to its management loop; copying the current full module exposed a newer
photo-cache dependency and was corrected before acceptance. Regression
coverage checks cadence, missed deadlines and packaging. All 145 terminal
tests completed (three platform skips), four packaging tests passed, and
focused lint and installer shell syntax checks passed.

A 50-second quiet 720p call validated native rendering after the driver change:
all 40 settled samples on each terminal had active received video, with median
received rates of 14.95 fps on Windows and 14.99 fps on the Pi. Both directions
retained audio traffic; the Pi screenshot showed the remote moving pattern
and its local-camera inset. Picom used about 5.9 MB RSS and 1.35% of one CPU
core during a 20-second sample, with no throttling. The first attempt was
aborted by a test-only ctypes audio-meter query after engine recreation;
the repeat omitted that query and completed normally. Restored normal terminal
processes and the Pi's saved 80% speaker level. Saved 1080p call preferences
remain as the user requested; this 720p rendering check does not resolve the
separate 1080p sender issue below.

### Presenter status and post-restart input recovery — 2026-10-11

After the display tests, the Presenter remained Bluetooth-connected (95%
battery), and term2 had its HID/input descriptors open. Button events reached
the app, but TV control repeatedly consumed them to reveal the terminal.
The observer was stuck on `/dev/cec1`: the running kernel still forced both
HDMI ports connected from the earlier recovery boot. Only `/dev/cec0` had a
256-byte EDID and enabled scanout; HDMI2 was disabled, empty and had physical
address `f.f.f.f`. Prefer EDID-bearing connected outputs, then enabled scanout,
while retaining the current adapter on equal evidence. The disconnected
standby fallback and explicit-adapter behavior remain intact. Deployed and
restarted the observer on `/dev/cec0`; the user confirmed all buttons work.
The first press after rediscovery spent about 4.8 seconds selecting/settling
HDMI. Once visibility was observed, cached routing avoided that wake sequence.

Added an antialiased Bluetooth symbol beside the top-right connectivity
indicators. Green means the Presenter input device is available, red/slashed
means unavailable, and grey means the platform cannot report this status.
Windows is currently grey; this Linux HID reader must not falsely report a
Windows remote disconnected. Status is part of the redraw signature and uses
existing device discovery/disconnect events, without shell polling on Tk.
Expanded both header side columns equally to preserve centered call names.
Verified the green icon on the Pi screenshot. All 146 terminal tests completed
(three platform skips), including forced-HDMI selection and device-status
transitions; focused lint passed.

## Pi 4 resolution comparison — 2026-10-11

Tested the C20 terminal with its normal UI/local preview and VSync compositor
at 720p HDMI. The PC sent a moving synthetic picture at the corresponding
resolution to exercise Pi decoding as well as camera encoding. After the first
run, reduced the Pi speaker from 80% to 10% and lowered test playback gain.
Resolution overrides were limited to test processes; server presets were not
modified. Both endpoints recorded media metrics; Pi CPU/temperature/throttling
were sampled every two seconds. Excluded ten startup seconds from settled
frame-rate comparisons.

| Requested preset | Observed live-call result | Pi CPU, mean of total four-core capacity | Peak temperature |
| --- | --- | --- | --- |
| 480p | 90-second run and 60-second repeat stayed live around 15 fps, but Pi output adapted to **320×240**; PC-to-Pi remained VGA. Not a full VGA-send qualification. | About 20% in repeat | 53°C in repeat |
| 720p | 90-second run and three-minute repeat passed. Approximately 15 fps in both directions at **1280×720**, without observed downscaling. | 26% in longer repeat | 56.5°C |
| 1080p | Pi decoded incoming **1920×1080** around 15 fps, but Windows decoded **zero** Pi frames during 90 seconds and logged OpenH264 errors. | 42% | 58°C |

The three-minute 720p repeat had active decoded video in every one of its
169 settled samples on both ends, continued audio traffic, and no reported
RTCP packet loss. Pi-camera receive rate at Windows was 14.06–16.95 fps
(median 14.95); the Pi received the PC pattern at 13.74–15.78 fps (median 14.99).
Eight Windows samples omitted received dimensions, while the remaining 161
reported 1280×720; all Pi samples reported 1280×720 in both directions. No
undervoltage, throttling or new USB disconnect was observed during the tests.

Isolated the 1080p failure with the existing native camera/codec roundtrip:
FFmpeg decoded 146 full-HD frames and OpenH264 147 in ten seconds, with zero
wrong-size frames and zero queue drops. Native compilation passed with
`-Wall -Wextra -Werror`. The Pi therefore has basic full-HD codec capacity,
but its live 1080p path is not usable yet; investigate negotiation/transport/
Windows decoding rather than assuming CPU exhaustion. A 15 fps send statistic
alone would have incorrectly passed the failed call.

**Initial recommendation (superseded by the decoder fix below):** use 720p/15 fps for calls. These short tests support that
setting on the current Pi 4, PSU, C20 and Wi-Fi; they do not certify unattended
endurance. The normal terminal was restored after testing. See
[hardware measurements](docs/pi-hardware-video.md#pi-4-call-measurements--11-october-2026).


## Callback tags and cancellation — 11 October 2026

Pending outgoing callback requests now show a purple return-arrow badge on the contact, separate from missed-call notifications. The badge alone indicates the pending request; the persistent text beneath the contact name was removed following user feedback. Press RED (Teams) to open cancellation confirmation, then GREEN (Mute/Yes) to cancel or RED (No) to keep the request. For an offline contact, GREEN also opens cancellation when a request already exists; available contacts can still be called normally.

The terminal uses the existing authenticated cancellation endpoint. Tags change after server acknowledgment and refresh on expiry/completion independently of configuration version. A poll started before a successful mutation cannot restore a cancelled tag, and a late result cannot replace an incoming-call screen. Failed cancellation keeps the request visible.

Validation: eight callback regression tests, the full terminal suite (154 tests, three platform skips), lint, and the isolated native Windows callback scenario passed. The live scenario checks creation, tagged contacts, declining cancellation, confirmed cancellation and server persistence, then notification/call completion. No request was sent to real contacts for these tests.

Also reduced the Bluetooth status image from 30 to 22 pixels, vertically centered it, and added six pixels of separation before the terminal/network indicators.

Deployment: applied the callback changes selectively to the older Pi release, preserving its working display/timing adaptations. Verified the badge, cancellation screen and Bluetooth spacing on the Pi at 1280×720 using an in-memory request with network services disabled. Restored the normal Pi service and restarted term1 with the updated code.


## Presenter motion volume — 11 October 2026

Measured the paired Presenter+ on the Pi: Pointer uses eight-byte `04/3d` press/release reports, and ten-byte `03` mouse reports carry signed little-endian relative Y at offset four. Holding Pointer now enables vertical motion to adjust C20 playback volume; horizontal or unheld motion is ignored. Duplicate press reports and other interfaces cannot release or reset the held gesture. Disconnect releases it.

The right-side vertical bar shows the requested percentage while held and for two seconds after release. A red exclamation mark reports mixer failure. Motion accumulates at 64 units per two percentage points (doubled at the user's request), clamps to 0–100, discards overshoot at the limits and resets residual movement on release. Mixer writes are capped at ten per second and coalesced on one worker, keeping native call and Tk processing responsive. C20 microphone gain, mute and TV/CEC state are untouched. The local level survives media-engine recreation during this app session; a changed server default overrides it when applied, and restarting restores that default.

Validation: 161 terminal tests passed (three platform skips), including signed-motion decoding, hold/release/disconnect and duplicate filtering, jitter, limits, throttling, auto-hide, engine reconfiguration and mixer failure recovery. Deployed selectively over the older Pi release. Real remote motion changed the ALSA PCM level, the 1280×720 screen capture showed the bar, and the user confirmed direction, response, release and disappearance. No test audio was played.

## Full-HD receive fix — 11 October 2026

The reported pixelated call was transmitting only 320×240 from term2 at about
334 kbit/s, although the C20 V4L2 capture format was 1920×1080 MJPEG. Controlled
tests exposed a camera setup error path: MediaStreamer ignores GET_VIDEO_SIZE
failure and retains its 320×240 default. The camera filter now returns the
requested dimensions even on error, while still refusing unsupported capture
formats. Camera open/format failures now include their actual reason in logs.

Full-resolution transmission then reproduced the older Windows receive failure.
A synthetic Pi-encoded 1080p stream decoded directly in OpenH264 but produced
zero frames through the bundled SDK adapter, without USB, networking or a server.
The adapter rewrites valid `00 00 03 00 xx` H.264 data and corrupts the stream.
A local Windows receive filter now preserves NAL bytes and delegates decoding
to the same pinned OpenH264 library. It supports fragmented RTP, in-band and SDP
parameter sets, format notifications and bounded recovery feedback. SDK encoding,
camera acquisition, SIP and rendering remain shared with the existing engine.

Repeated PLI/FIR requests previously forced nearly every Pi picture to become a
keyframe, increasing traffic to roughly 20 Mbit/s. Requests now coalesce to one
per second. No server or network-buffer change was needed for successful calls.

After fixing decoding, a 180-second two-way webcam call delivered 1920×1080 on
both terminals throughout all post-startup samples. Windows received an average
15.14 fps (13.53–16.85 measured range); Pi received 15.00 fps (13.93–15.24).
Windows received about 2.59 Mbit/s and reported zero video loss; the Pi recorded
one small sender-loss report, peaking at 0.78%, without losing decoded video.
Audio traffic flowed both ways. A term1 screenshot showed visibly sharper faces,
clothing and small objects. This establishes short-call 1080p viability, not
unattended endurance.

Separate C20 USB timeouts/disconnections still occurred in earlier tests. The
user confirmed it remains connected directly to the Pi. A powered hub remains
recommended for that device issue; the observed failures do not establish CPU
exhaustion. After the long test, the Pi reported 52.1°C and no throttling.
The next normal call again encountered USB I/O timeouts at capture startup;
resetting the C20 restored access. Do not treat the passing long call as a fix
for this independent startup fault.

Validation: 161 terminal tests passed (three platform skips); native warning-clean
builds and lint passed. The Windows synthetic regression decodes all three
1080p frames with both in-band and SDP parameter sets. The Pi recovery regression
verifies dimensions after a missing-camera error and coalescing of 1,000 recovery
requests. See `build_tools/tests/h264_decoder_native.py` and
`build_tools/linux/test-video-recovery.c`.

## Local inset quality — 11 October 2026

After the user confirmed sharp received 1080p video, the Pi's self-view still
showed jagged detail. It was shrinking the full camera image directly into a
roughly 240×130 window with the SDK's bilinear GPU filtering. The Linux display
adapter now averages pixels into an intermediate 480×270 image before the
final inset resize. This operates only on the small display branch; camera
capture, encoding and the incoming main picture retain their resolution.

The user confirmed the inset looks better. A 90-second follow-up call retained
live 1920×1080 in every sample after startup: term1 received 15.25 fps on average
and term2 15.04 fps, with zero reported video receive loss on either side.
The Pi showed 57.9°C and no throttling. Synthetic luma/chroma stripes validate
the averaging and unchanged source, with about 8–9 ms CPU time per frame.
The renderer method namespace is covered after the first live trial exposed
an incompatible registration; the corrected trial passed. Terminal tests
(161, three skipped), native compilation and lint passed. Test-only volume
attenuation was removed by restoring the normal applications; C20 playback
was restored to 80%.
