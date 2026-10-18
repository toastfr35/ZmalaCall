# Server requirements

Generated from [Doorstop SERV records](requirements/server/). Edit the YAML records, then run `build_tools/publish-requirements.ps1`.

- [1.0 Independent server and LAN administration _(SERV001)_](#SERV001)
- [2.0 Account management _(SERV002)_](#SERV002)
- [3.0 Group permissions _(SERV003)_](#SERV003)
- [4.0 Derived terminal contacts _(SERV004)_](#SERV004)
- [5.0 Authenticated SIP and media routing _(SERV005)_](#SERV005)
- [6.0 Valid caller cancellation _(SERV006)_](#SERV006)
- [7.0 Online presence _(SERV007)_](#SERV007)
- [8.0 Callback lifecycle _(SERV008)_](#SERV008)
- [9.0 Callback delivery _(SERV009)_](#SERV009)
- [10 Dark administration pages _(SERV010)_](#SERV010)
- [11 Selected terminal card _(SERV011)_](#SERV011)
- [12 Terminal settings _(SERV012)_](#SERV012)
- [13 Printable QR downloads _(SERV013)_](#SERV013)
- [14 Maintenance queue and isolation _(SERV014)_](#SERV014)
- [15 State persistence and device isolation _(SERV015)_](#SERV015)
- [16 Text message notifications _(SERV016)_](#SERV016)
- [17 Callback email reminders _(SERV017)_](#SERV017)
- [18 Pi server installation and service controls _(SERV018)_](#SERV018)

<a id="SERV001"></a>

## 1.0 Independent server and LAN administration _(SERV001)_

The Node.js server shall run independently of the terminal runtime, with Windows start/stop scripts and a Raspberry Pi systemd deployment, same-LAN SIP over UDP/TCP and an audio/video relay. LAN browsers may perform first-time shared-password setup and authenticate for administration. Password changes shall revoke existing sessions; sessions shall expire after eight hours and on restart. Mutations shall enforce same-origin checks. HTTP shall be limited to a trusted LAN; optional HTTPS shall reject remote plaintext administration when enabled. Local password-file removal while stopped shall deliberately reopen setup. Linux portrait conversion shall require Python with Pillow.

> `zmala_server/main.js`

*Parent links:* [ZMC001 Independent platform components](product_requirements.md#ZMC001)

<a id="SERV002"></a>

## 2.0 Account management _(SERV002)_

Administration shall create, edit and delete phone and terminal accounts with editable username, display name, password, one-to-ten unique email addresses and an optional picture on a shared SIP domain/server. New accounts shall require an email address. Existing accounts without addresses shall be identified for administrator completion; migration shall not invent addresses or change credentials. Each terminal shall have a persistent serial number independent of its account username. Administration shall associate a terminal serial with a terminal account from the Terminals page. Reassignment shall preserve device credentials, hardware settings and console history with the serial, retain identity and groups with the account, and reject changes during active calls. Active calls shall prevent destructive account changes. Contact email addresses shall remain in administration and shall not appear in terminal configuration.

> `zmala_server/tests/admin.test.js`
> `zmala_server/tests/callback-emails.test.js`

*Parent links:* [ZMC002 Accounts and shared groups](product_requirements.md#ZMC002)

<a id="SERV003"></a>

## 3.0 Group permissions _(SERV003)_

Administration shall create, edit and delete groups and their memberships. Two distinct accounts shall be permitted to call exactly when they share at least one group. Accounts may join several groups; permission shall be symmetric, nontransitive and disabled for unknown or self accounts.

> `zmala_server/tests/server.test.js`

*Parent links:* [ZMC002 Accounts and shared groups](product_requirements.md#ZMC002)

<a id="SERV004"></a>

## 4.0 Derived terminal contacts _(SERV004)_

Each terminal configuration shall derive callable contacts from current shared groups, use account names/pictures and sort by display name. Terminals shall not support contact renaming, picture overrides or custom ordering.

> `zmala_server/tests/server.test.js`

*Parent links:* [ZMC002 Accounts and shared groups](product_requirements.md#ZMC002)

<a id="SERV005"></a>

## 5.0 Authenticated SIP and media routing _(SERV005)_

The server shall authenticate registrations and call requests, enforce groups and add a per-terminal proof validated by the recipient. Signaling shall follow authenticated peer flows and media shall use relay addresses. Calls shall not be recorded by default. Stream framing shall reject malformed, duplicate or excessive Content-Length values and expire unfinished messages within 30 seconds. ACK requests shall retain no proxy contexts; other contexts shall have per-peer and global limits and a 90-second lifetime. Changes to established media shall remain staged until successful negotiation; rejected changes shall preserve the active targets. An accepted zero media port shall close the corresponding stream. In-dialog INVITE without an SDP offer shall receive 488; overlapping negotiations shall receive 491.

> `zmala_server/tests/server.test.js`
> `zmala_server/tests/sip-bounds.test.js`

*Parent links:* [ZMC004 Audio and video calls](product_requirements.md#ZMC004)

<a id="SERV006"></a>

## 6.0 Valid caller cancellation _(SERV006)_

The server shall relay cancellation of a ringing call to the called terminal so it stops ringing. Forwarded SIP CANCEL shall contain the required Max-Forwards header and preserve the INVITE transaction identity and authenticated registration flow.

> `zmala_terminal/tests/callbacks_live.py`

*Parent links:* [ZMC010 Contact notifications and caller cancellation](product_requirements.md#ZMC010)

<a id="SERV007"></a>

## 7.0 Online presence _(SERV007)_

Terminal configuration and authenticated availability checks shall report account online state independently of configuration version. A registered phone becoming unresponsive shall be marked unavailable on the terminal within 15 seconds. The server shall probe each registration flow every five seconds with a five-second response timeout, exclude unreachable accounts from online status, dialing and callback notification delivery, and continue checking their unexpired registration flows for recovery. A successful fresh registration or reachability response shall restore online status. Expired or absent registrations shall remain unavailable.

> `zmala_server/tests/admin.test.js`
> `zmala_server/tests/presence.test.js`
> `zmala_terminal/tests/callbacks_live.py`

*Parent links:* [ZMC003 Accessible physical controls](product_requirements.md#ZMC003)

<a id="SERV008"></a>

## 8.0 Callback lifecycle _(SERV008)_

Only an authenticated terminal shall create a callback request as itself to a currently permitted contact. Requests shall persist atomically and deduplicate active requester/recipient pairs. The Callbacks page shall configure email-reminder and request-removal delays in hours, including fractional hours, measured from request creation. Defaults shall be one hour for email and four hours for removal. Removal shall be later than email. Changes shall apply to pending requests. After the removal deadline, pending requests shall be removed from persisted data and all views. Connected calls in either direction shall complete requests. Removing permission, deleting accounts or converting the requester to a phone shall cancel them; username edits shall preserve them. Completed and cancelled requests shall remain in bounded history.

> `zmala_server/tests/callbacks.test.js`
> `zmala_server/tests/callback-emails.test.js`

*Parent links:* [ZMC007 Callback requests](product_requirements.md#ZMC007)

<a id="SERV009"></a>

## 9.0 Callback delivery _(SERV009)_

The server shall deliver pending phone callback notifications as basic UTF-8 SIP MESSAGE over the authenticated registration flow after registration or reachability recovery, including the requester SIP address. Accepted delivery shall be recorded once; failures shall retry no more than once a minute while online. Periodic checking shall occur every five seconds. SIP acceptance shall not imply the user read the notification. Terminal recipients shall receive requests through configuration polling.

> `zmala_server/tests/callbacks.test.js`

*Parent links:* [ZMC007 Callback requests](product_requirements.md#ZMC007)

<a id="SERV010"></a>

## 10 Dark administration pages _(SERV010)_

Administration shall remain in English with separate dark pages for overview, accounts, groups, terminals, callbacks and activity, using modal dialogs for relevant edits and confirmation. It shall omit the removed tiny header bars, marketing text, server-online badge and footer; recent events shall appear only on Activity.

All administration pages, sign-in and editing dialogs shall be usable on phones and PC monitors, including viewport widths from 320 to 1920 CSS pixels. Navigation and account actions shall remain accessible without horizontal page scrolling. Phone account rows shall stack with column labels; wider screens shall retain the table. Dialogs shall fit the available viewport and scroll vertically. Narrow-screen and touch layouts shall provide at least 44-pixel button targets and readable form inputs, including long account names, device names and connection details.

Background refreshes shall not detach the focused control. Connection-detail copying shall support LAN HTTP where the browser permits it and report any failure inside the open dialog, with manual-copy guidance. Closing or changing a terminal console shall invalidate responses from its previous opening.

Account edits/deletion confirmations, terminal settings and console shell editors shall submit the configuration revision observed when opened. Conflicting saves shall return HTTP 409 without changing state and show reload/reopen guidance. Polling shall not silently advance a draft's revision. A pending account photo upload shall not continue saving after its editor closes or changes account. Setup-download errors shall remain observable by the administration action handler.

> `zmala_server/web/admin.js`

*Parent links:* [ZMC009 Administration and persistent state](product_requirements.md#ZMC009)

<a id="SERV011"></a>

## 11 Selected terminal card _(SERV011)_

The Terminals page shall show one terminal card selected by dropdown. Its account-association and terminal settings forms shall have separate save actions and retain unsaved edits. Settings shall be grouped into Calls, Video & audio and General, with every registered control attached to the visible form, including frame rate. Account identity, credentials and portrait editing shall remain on Accounts. Wi-Fi QR PDF, server QR PDF and console downloads/actions shall be in that card. Contacts shall be managed through Groups and Accounts.

> `zmala_server/web/admin-terminals.js`

*Parent links:* [ZMC009 Administration and persistent state](product_requirements.md#ZMC009)

<a id="SERV012"></a>

## 12 Terminal settings _(SERV012)_

Administration shall configure each terminal language, camera, microphone, speaker, audio processing, video resolution and command shell. Video resolution shall be independently selectable as 480p (640×480), 720p (1280×720, default) or 1080p (1920×1080). Windows and Linux terminals shall apply server video settings automatically when idle, defer changes during calls, offer independent outgoing frame-rate targets of 10, 15 (default), 20, 25 or 30 fps per terminal with matching sending bandwidth presets and receive capacity independent of the local sending target, and prefer server settings over legacy local experiment overrides. Actual frame rates shall depend on hardware and network capacity. Shell options shall be Windows PowerShell, PowerShell 7 and Command Prompt on Windows, and sh/bash on Linux. Selecting a shell incompatible with the terminal OS shall fail that command explicitly. The Terminals page shall configure auto-answer enable/disable and a five-to-six-hundred-second answer delay. Account names, pictures and credentials shall be managed on the Accounts page. Language configuration shall affect only the terminal display. Applying a native terminal configuration shall publish its applied revision only after engine setup succeeds. Failures shall release failed engines and retry the latest desired configuration while idle, with a five-second backoff. C20 mixer subprocesses shall run on one background worker that coalesces superseded volume values.
An authenticated device shall be able to update only its own language, auto-answer enable/delay, automatic framing, speaker volume, carousel portrait count and TV return timeout. Writes shall compare the previous values of edited fields, reject conflicting edits, preserve all other settings, and acknowledge only after persistence. Retrying an already-applied value shall not advance the configuration revision, but shall still await the persistence barrier. Ringing cleanup and the terminal outgoing/incoming timers shall allow the configured automatic-answer delay plus a grace period.

> `zmala_server/tests/admin.test.js`

*Parent links:* [ZMC006 Terminal languages](product_requirements.md#ZMC006)

<a id="SERV013"></a>

## 13 Printable QR downloads _(SERV013)_

Administration shall download single-page A4 Wi-Fi and terminal-server QR PDFs with a large readable QR and quiet border. Wi-Fi generation shall accept SSID/password without saving them on the server. Server QR shall contain the selected terminal versioned enrollment URL, device identity and token. Access shall require administrator authentication.

> `zmala_server/tests/setup.test.js`

*Parent links:* [ZMC005 Reset and QR setup](product_requirements.md#ZMC005)

<a id="SERV014"></a>

## 14 Maintenance queue and isolation _(SERV014)_

Administrator-authenticated console actions shall queue commands per terminal and show results. A terminal token shall claim/report only its own jobs with a unique lease. The selected shell shall be stored with each new job. There shall be at most ten pending jobs per terminal, five-to-120-second timeouts and at most 64 KiB combined output. Lost jobs shall not be automatically rerun. Job ownership shall use the immutable device serial rather than its account username. Retirement or conversion to a phone shall prevent replacement devices from claiming work or accessing old output. Legacy records without an established device owner shall never execute. Combined output shall mean at most 65,536 UTF-8 bytes after decoding, with an HTTP result-body cap of 400,000 bytes to accommodate JSON escaping. Result retries with the same lease shall commit already-completed in-memory results after a temporary storage failure without executing the command again.

> `zmala_server/tests/console.test.js`
> `zmala_server/tests/reliability.test.js`

*Parent links:* [ZMC008 Remote maintenance](product_requirements.md#ZMC008)

<a id="SERV015"></a>

## 15 State persistence and device isolation _(SERV015)_

Accounts, groups, settings, pictures, callbacks and console history shall persist across server restarts. Configuration and jobs shall be scoped to the authenticated terminal. Credential-bearing bootstrap/admin shortcuts and setup artifacts shall remain private. Runtime snapshot writes shall be asynchronous and ordered per file. Each mutation shall await the writers it changes before success; unrelated read-only management requests shall remain available during a console or callback save failure. Subsequent commit barriers shall retry failed latest snapshots. /health shall report process liveness; /ready shall return 503 while a latest snapshot has a known unresolved failure and 200 after recovery. Atomic replacement shall not be described as a cross-file transaction or a power-loss fsync guarantee.

> `zmala_server/tests/admin.test.js`
> `zmala_server/tests/reliability.test.js`

*Parent links:* [ZMC009 Administration and persistent state](product_requirements.md#ZMC009)

<a id="SERV016"></a>

## 16 Text message notifications _(SERV016)_

The server shall authenticate phone-originated SIP text messages and forward them only to an online terminal sharing a group with that phone. It shall route over the terminal's registered flow, replace client-supplied proof with terminal-specific authenticated sender/message proof, and reject unauthorized, unsupported, empty or oversized messages. An unavailable terminal shall return SIP 480 rather than queue the text. Text notification routing shall not create a call or expose message content in application event logs. Server-generated callback notifications to phones shall continue to operate independently.

> `zmala_server/sip-messages.js`
> `zmala_server/tests/messages.test.js`

*Parent links:* [ZMC010 Contact notifications and caller cancellation](product_requirements.md#ZMC010)

<a id="SERV017"></a>

## 17 Callback email reminders _(SERV017)_

After the email deadline, a still-pending callback shall generate a separate email to every address on the contact's account, independently of SIP notification and online status. Each accepted recipient shall be persisted and skipped on retries or restart. A failed address shall not block other recipients. Failed delivery shall retry no more often than once a minute until completion, cancellation or removal. The Callbacks page shall configure SMTP host, port, security, optional credentials and sender, enable/disable reminders and check connection/authentication without sending mail. Stored SMTP passwords shall be omitted from admin responses, blank password input shall preserve them, and explicit clearing shall be supported. STARTTLS and TLS shall validate certificates. SMTP acceptance shall not imply inbox delivery or reading.

> `zmala_server/callback-emails.js`
> `zmala_server/callback-mailer.js`
> `zmala_server/tests/callback-emails.test.js`

*Parent links:* [ZMC007 Callback requests](product_requirements.md#ZMC007)

<a id="SERV018"></a>

## 18 Pi server installation and service controls _(SERV018)_

A Windows GUI/headless installer shall validate SSH, Raspberry Pi OS Lite 64-bit Trixie, supported hardware, Ethernet access and storage before deployment. It shall install automatic startup, Ethernet-only SSH and low-write settings while keeping server HTTP/SIP/media available on all IPv4 interfaces. Optional migration shall preserve accounts, credentials, portraits and persisted server data without replaying in-flight console commands. Installed state shall live under /var/lib/zmalacall-server; updates shall preserve it. Authenticated administration shall enable/disable wired SSH persistently without stopping server services. SSH shall remain enabled during installation. Installation failure shall be reported, and verification shall distinguish dependency/configuration changes from application-release rollback.

> `build_tools/server_installer/backend.py`
> `build_tools/tests/test_server_installer.py`
> `zmala_server/server-ssh.js`

*Parent links:* [ZMC001 Independent platform components](product_requirements.md#ZMC001)

