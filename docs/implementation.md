# Implementation guide

The terminal, server and Windows build tools have separate entry points. Runtime state stays under each component's `data/` directory; source modules never contain account credentials. Generated administration assets and requirements catalogues are marked as generated and rebuilt from their source files.

## Terminal

| Source | Responsibility |
|---|---|
| `zmala_terminal/main.py` | Compose the application, restore enrollment, bind physical-button equivalents and apply configuration |
| `model.py` | Platform-independent call state, contact selection and unread notification counts |
| `call_control.py` | SIP events, availability preflight and callback requests |
| `management.py` | Dispatch worker messages, refresh presence and run UI timers |
| `setup_flow.py` | Factory reset, camera lifecycle and Wi-Fi/server enrollment transitions |
| `ui/display.py` | Tk layout, text sizing, connectivity and missing-video overlay |
| `ui/carousel.py`, `ui/confirmation.py` | Animated portraits, notification badges and full-screen questions |
| `theme.py`, `icons.py`, `text_renderer.py` | Shared colors/icon geometry and platform-selected text/picture rendering |
| `configuration.py`, `config_validation.py` | Authenticated HTTP retrieval, validation and cache policy |
| `provisioning.py`, `wifi.py` | Enrollment persistence, QR parsing, reset gesture and platform-selected Wi-Fi |
| `json_storage.py`, `missed_calls.py` | Atomic local snapshots and account-scoped unread counts |
| `engine.py`, `linphone_api.py` | Call/media behavior, native ABI declarations and platform-selected library loading |
| `qr_scanner.py`, `qr_worker.py`, `native_qr.py` | Parent/child camera protocol and native accountless preview |
| `maintenance.py`, `process_job.py` | Shell construction, command output, outbound console polling and child-process ownership |

`Terminal` owns state and resource lifetimes. Its display and controller classes operate on that one host rather than maintaining copies of call/configuration state. The model has no Tk or native SDK dependency. Keep business transitions in the model or call controller, and drawing in `ui/`.

`platforms/` contains Windows GDI+/WLAN/Job Object and Linux Pango/Cairo/NetworkManager/POSIX implementations. `platforms/native_runtime.py` locates native libraries and resources; the call engine and ABI are shared. Linux QR preview uses OpenCV/ZBar in the same isolated-worker protocol; Windows retains its native preview bridge. See [Linux terminal](linux-terminal.md) for deployment and hardware-test limits.

Tk and Liblinphone iteration/callbacks run on the UI thread. HTTP and Wi-Fi workers return results through the message queue. Every enrollment-sensitive result carries a generation number; reset advances that number and discards old results. Dial and callback operations also use a serial number to reject cancelled attempts. The UI thread owns timer and network-check scheduling.

Native callbacks and DLL-directory handles must remain referenced while their core is alive. Call pointers borrowed from callbacks become owned references only through `hold_call()`, and are released with their video callbacks. Engine shutdown and terminal shutdown are idempotent. The QR camera runs in a separate process so a native decoder failure can leave the setup screen open for retry.

Unread counts persist by account identity. Older contact-only flags load as one notification. Production mutations use the model's notification methods; opening either confirmation clears that contact's count, even if the user cancels. SIP text contents are never persisted with these counts.

## Server

| Source | Responsibility |
|---|---|
| `zmala_server/main.js` | Construct services, write bootstrap files and start/stop the process |
| `http/handler.js`, `http/responses.js` | Host/origin checks, authentication boundary, static assets, body limits and response headers |
| `http/device-routes.js` | Token-scoped configuration, reachability, callbacks, status and console claims/results |
| `http/admin-routes.js` | Account/group administration, settings, printable setup and console management |
| `store.js`, `accounts.js` | Authoritative configuration, account operations and derived views |
| `defaults.js`, `validation.js`, `migrations.js` | Fresh configuration, input validation and legacy schema conversion |
| `json-file.js`, `snapshot-file.js`, `history.js` | Startup/tool snapshots, asynchronous ordered configuration snapshots and bounded completed histories |
| `sip-server.js` | Transport, registration handling and call-dialog routing/lifetimes |
| `sip-guards.js`, `sip-transport.js` | Request/hop validation and cancellation checks before SIP transaction caching |
| `types/`, `tsconfig.json`, `tsconfig.admin.json` | Shared API/data contracts, narrow dependency declarations and strict runtime/browser source checking |
| `registrations.js` | Exact-flow OPTIONS probes and the shared online predicate |
| `sip-messages.js` | Authenticated phone text notifications and SIP callback delivery |
| `media.js` | RTP/RTCP sockets and SDP rewriting |
| `callbacks.js`, `console-jobs.js` | Persisted callback and remote-command lifecycles |
| `callback-settings.js`, `callback-emails.js`, `callback-mailer.js` | Hour-based deadline validation, per-recipient reminder retries and asynchronous SMTP transport |
| `photos.js`, `setup-pdf.js` | Asynchronous picture conversion and printable QR generation |

Resolve a terminal identity from its bearer token, never a request-supplied terminal ID. Admin routes are called only after the central authentication check; phone-to-terminal SIP messages have their own digest, group and per-terminal proof checks. The CANCEL-header compatibility wrapper must be installed after `proxy.start()` because that library replaces `sip.send` during startup.

Configuration mutations validate before changing shared state and commit through `changed()`. Reachability changes independently of `configuration_version`; terminal polling must update online/offline status even when that version is unchanged. A probe retains the exact registration object so a timeout or reply from an old flow cannot change a replacement registration. Unreachable unexpired flows are retained for recovery checks.

Production configuration saves serialize the current state into an immutable string and queue asynchronous temporary-file writes and renames through one `SnapshotFile` per file. Admin responses wait for the store's persistence barrier; bootstrap updates also wait for the store before publishing enrollment files. Failed writes return a sanitized HTTP error; a subsequent commit barrier retries the latest failed snapshot. Unstarted revisions coalesce into one latest snapshot, and all affected acknowledgements wait for its commit. Memory may already contain the mutation when disk persistence fails. Shutdown waits for pending configuration and bootstrap writes. These renames provide atomic replacement, not an fsync durability guarantee.

Static assets and account pictures use asynchronous reads. PDF generation loads the optional Windows font asynchronously once, then passes its bytes to PDFKit. Startup and standalone setup tools retain synchronous persistence. Production callback and console snapshots use asynchronous writers. Callback recipient progress, command leases and results await their own commit barriers; unrelated device reads do not wait for these writers. /health reports liveness and /ready reports known unresolved persistence failures. See [platform and recovery notes](reliability.md) for retry, migration and durability limits.

`npm run typecheck` checks every first-party server runtime module and every `web/admin-*.js` source module with strict `checkJs`. This includes SIP dialogs, registrations and messages, startup, callback delivery, SMTP, console jobs, photos and PDF provisioning. Shared contracts cover persisted records, terminal settings, media/dialog ownership and admin HTTP snapshots. `types/http.ts` defines the service operations available to routes; request fields remain `unknown` until validated. Node executes the existing JavaScript directly; no deployment transpilation step is required. The generated admin bundle, third-party dependencies and JavaScript test fixtures are excluded from type checking.

The browser API helper derives response types from shared route contracts; admin routes check the snapshot before sending it. JSON decoding remains a trust boundary, not a runtime schema validator. `types/admin-dom.ts` describes static IDs in `admin.html` and form controls; keep it synchronized when editing the markup. Required-element helpers fail clearly if required markup disappears. Optional elements and dirty-form searches retain nullable DOM lookups. `types/admin.ts` describes shared controller state. Controllers render only after an admin snapshot loads.

Legacy configuration uses a separate migration staging shape in `types/migrations.ts`. It allows obsolete or incomplete fields only while migrations run. Account type changes publish a complete replacement identity, removing terminal enrollment fields when converting to a phone account. The selected terminal can be null when no terminal accounts remain. Narrow declarations for the maintained SIP dependency live in `types/sip.d.ts` and `types/sip-proxy.d.ts`; explicit compiler paths prevent local file-dependency links from including vendored JavaScript in the strict program.

Terminal status reports validate diagnostic strings, configuration versions, registration flags and device lists before replacing the last valid report. Their timestamps are assigned by the server. Closing the SIP service clears dialog ownership before releasing media, so asynchronous SDP work cannot forward a call after shutdown. Regressions exercise both boundaries.

The SIP dependency is pinned to the local `vendor/sip` copy of npm `sip@0.0.6`, with its MIT license and original-file hashes retained. A real UDP regression exposed a transaction-cache issue: rejecting a forged CANCEL inside the router was too late, because it could reserve the legitimate caller's transaction key. The local pre-transaction hook rejects cancellation unless the transport peer, From tag, CSeq and Via branch match the pending INVITE. Cancellation while SDP allocation is pending terminates the original INVITE without forwarding a late offer. Late SDP responses recheck dialog ownership before connecting or forwarding. See [patch provenance and upgrade instructions](../zmala_server/vendor/sip/ZMALA-PATCH.md). The application also validates required SIP fields and hop limits before routing. These targeted checks do not constitute a complete protocol audit.

Media allocations are shared while UDP bind is pending. Closing a session marks it closed before releasing sockets, so a late allocation is reclaimed. Late dialog responses cannot reopen a released relay. Picture conversion runs outside the Node event loop with two converter slots and ten admitted requests, deduplicates identical in-flight sources, checks dimensions before decoding, uses unique intermediate paths and publishes by content hash. Windows uses PowerShell; Linux uses Python/Pillow. Repeated uploads reuse existing files rather than replacing a photo that Windows may have open. Established-call media changes are staged until successful negotiation, with rejected updates preserving active targets and accepted disabled streams releasing sockets.

Callback policy stores hour delays (`email_after_hours`, `remove_after_hours`) in server configuration. `Callbacks` derives timestamps from the request's original creation time, including during restart recovery if saving policy and request snapshots was interrupted. Removal deletes pending records; it does not retain an expired history row. Connected/cancelled requests retain the existing bounded history behavior.

The reminder worker runs independently of SIP notifications, allows three concurrent requests and sends each recipient separately. Accepted addresses persist before moving to the next recipient; errors do not block other addresses and retry after 60 seconds. Every send and late result rechecks request ownership, state, expiry and permission. SMTP acceptance can occur immediately before a server crash and snapshot write; stable message IDs help mail systems recognize duplicates but cannot guarantee exactly-once external delivery. Nodemailer handles STARTTLS/TLS with certificate validation; connection, greeting and socket timeouts bound unresponsive transports. Contact addresses and saved SMTP passwords are excluded from device-facing data; SMTP passwords are also excluded from admin responses.

Administration renders callback controls in `web/admin-callbacks.js`. Deadline and SMTP modals retain a configuration version to reject conflicting saves. Existing accounts without addresses remain operational after migration and display an email-needed hint; new account creation and email edits validate one-to-ten unique plain mailbox addresses.

## Administration and build tools

The administration client uses `web/admin-*.js` modules for accounts, groups, terminals, overview/activity/callbacks, console and QR setup. `admin-state.js` owns shared state and refresh hooks; `admin-shared.js` provides DOM, API and modal helpers. Terminal card builders separate account forms from device/display forms. Cached cards retain unsaved fields and picture URLs; unused image URLs are released when their owning view is discarded.

Styles are split under `web/styles/` into theme, tools, layout, pages, forms, responsive and terminal rules. Obsolete contact-editor and terminal-picker styles have been removed. Their order is explicit to preserve the cascade.

`build_tools/build-admin.cjs` generates `web/admin.js` and `web/admin.css` without requiring an installed build package. Edit the modules/styles, then rebuild; do not edit the generated files. The small script bundle accepts local named imports and exported functions/constants with unique top-level names. If richer module semantics become necessary, replace it with a standard bundler. The regular server startup rebuilds the assets, and the build check detects stale copies.

`processes.ps1` owns launcher locking, atomic process records and PID/executable/start-time verification. A stop script targets only its recorded component. `setup-runtime.py` verifies pinned package hashes and keeps interrupted downloads separate from committed packages. The camera bridge source documents its SDK-specific format-change and unmirrored-preview behavior.

## Verification

From the project root:

```powershell
npm.cmd ci --cache build_tools/runtime/npm-cache
npm.cmd run format:check
npm.cmd run build:check
npm.cmd run typecheck
npm.cmd test
& 'C:\msys64\ucrt64\bin\python.exe' -m unittest discover -s zmala_terminal/tests -p 'test_*.py'
& '.\build_tools\tests\process_controls.ps1'
& '.\build_tools\doorstop.cmd' --no-reformat --error-all --no-review-check
& '.\build_tools\publish-requirements.ps1'
```

Use `npm run format` to format JavaScript, TypeScript, HTML and source CSS and rebuild the admin assets. `npm run build:admin` only rebuilds those assets. Server runtime dependencies remain installed under `zmala_server/`; root development dependencies provide formatting, linting and type checking. `make lint` runs the combined source checks. The server tests include ordered persistence/failure recovery, responsive health checks while a save is blocked, asynchronous asset reads and real UDP cancellation checks; they use private fixtures without restarting the live server.

Terminal native/UI checks:

```powershell
& 'C:\msys64\ucrt64\bin\python.exe' zmala_terminal/tests/call_feedback_ui.py
& 'C:\msys64\ucrt64\bin\python.exe' zmala_terminal/tests/terminal_languages_ui.py
& 'C:\msys64\ucrt64\bin\python.exe' zmala_terminal/tests/contact_presence_ui.py
& 'C:\msys64\ucrt64\bin\python.exe' zmala_terminal/tests/provisioning_ui.py
& 'C:\msys64\ucrt64\bin\python.exe' zmala_terminal/tests/callbacks_live.py
```

Provisioning starts an isolated HTTP service and account, exercises the actual Windows command runner and stops its service on completion. Callback integration starts an isolated SIP/HTTP service and uses static cameras/file audio. UI-only checks read the configured server's contacts with a quiet engine and do not replace a live registration. `accounts_live.py` and `sip_peer.py` can target a separate fixture using `ZMALA_TEST_SERVER_STATE` set to its absolute `server.json` path; without it, they use temporary accounts on the configured server. Never run launcher or media checks that replace a live registration while that terminal is in use.

Regression checks cover stale enrollment results, malformed cached/HTTP objects, concurrent photo publication, media allocation cleanup, authentication, groups, callbacks, command leases, unread counts, all 95 display languages and native camera crash containment. The review also exercised the admin pages and modals through the Browser skill and a native outgoing call with video absent, sending, stopped and resumed while audio continued.
