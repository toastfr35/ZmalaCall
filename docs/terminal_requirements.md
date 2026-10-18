# Terminal requirements

Generated from [Doorstop TERM records](requirements/terminal/). Edit the YAML records, then run `build_tools/publish-requirements.ps1`.

- [1.0 Independent terminal launch _(TERM001)_](#TERM001)
- [2.0 Contact identity and carousel _(TERM002)_](#TERM002)
- [3.0 Contact availability _(TERM003)_](#TERM003)
- [4.0 Call confirmation _(TERM004)_](#TERM004)
- [5.0 Physical-button prompts _(TERM005)_](#TERM005)
- [6.0 Callback confirmation _(TERM006)_](#TERM006)
- [7.0 Incoming calls and auto-answer _(TERM007)_](#TERM007)
- [8.0 Active call controls _(TERM008)_](#TERM008)
- [9.0 Missing remote video _(TERM009)_](#TERM009)
- [10 Connectivity indicator _(TERM010)_](#TERM010)
- [11 Caller hang-up while ringing _(TERM011)_](#TERM011)
- [12 Missed-call badge _(TERM012)_](#TERM012)
- [13 Missed-call acknowledgment _(TERM013)_](#TERM013)
- [14 Missed-call persistence _(TERM014)_](#TERM014)
- [15 Manual callback availability notice _(TERM015)_](#TERM015)
- [16 Language application _(TERM016)_](#TERM016)
- [17 Factory reset access _(TERM017)_](#TERM017)
- [18 Factory reset scope _(TERM018)_](#TERM018)
- [19 QR enrollment sequence _(TERM019)_](#TERM019)
- [20 Stable camera QR scanning _(TERM020)_](#TERM020)
- [21 Command execution _(TERM021)_](#TERM021)
- [22 Interrupted or changed confirmation _(TERM022)_](#TERM022)
- [23 Text messages use missed-call badges _(TERM023)_](#TERM023)
- [24 Serial keypad host integration acceptance _(TERM024)_](#TERM024)
- [25 Presenter motion volume control _(TERM025)_](#TERM025)
- [26 Local settings with remote control _(TERM026)_](#TERM026)
- [27 Remote onboarding and status _(TERM027)_](#TERM027)
- [28 TV setup and idle restoration _(TERM028)_](#TERM028)

<a id="TERM001"></a>

## 1.0 Independent terminal launch _(TERM001)_

The terminal shall run on Windows and the documented Linux/Pi configuration with Tk and Liblinphone, support an optional fullscreen mode, and have separate start, stop and fresh unconfigured launchers. Starting it shall not implicitly start the server. The Pi installer shall validate Raspberry Pi OS Lite 64-bit Trixie and wired SSH before deployment, install boot services and dependencies, limit SSH to Ethernet, configure Argon fan control and low-write storage settings, and leave account identity to QR enrollment.

> `build_tools/start-terminal.ps1`

*Parent links:* [ZMC001 Independent platform components](product_requirements.md#ZMC001)

<a id="TERM002"></a>

## 2.0 Contact identity and carousel _(TERM002)_

The idle terminal shall show a dark carousel with a central selected portrait twice the width and height of neighboring portraits, side arrows and animated rotation. The server shall offer a per-terminal choice of three (default) or five portraits. The five-portrait layout shall fit 720p displays while reserving space for navigation arrows; contact lists shorter than five shall retain three positions. The setting shall persist and apply when idle. Layout changes shall preserve selection, alphabetical order, notification badges and rotation in both directions. Contacts shall use account display names and pictures, with initials for missing pictures. Every carousel contact, including the selected contact, shall keep its name inside the card below its picture and above the availability band throughout rotation. The idle layout shall omit the separate name below the carousel and collapse empty subtitle space. Idle mode shall omit clickable buttons, bottom instructions and the terminal name. Optional portrait downloads shall run independently of configuration and presence polling, on one worker with at most 40 queued paths. Partial or invalid cached portraits shall be replaced atomically after validation, with failed downloads retried no more frequently than once per minute. Cancelled enrollment workers shall not publish their downloaded portraits.

Rendering caches shall enforce both entry counts and estimated pixel-byte budgets, evicting least recently used entries individually. Images larger than their cache budget shall remain renderable without being retained. Cache eviction shall not invalidate images still displayed. Native source resources shall be released on eviction, replacement and shutdown. These budgets constrain retained cache payload, not transient decoding allocations or total process memory.

Downloaded and locally cached portraits shall undergo PNG/JPEG header checks before native decoding: at most 2 MiB encoded, 4096 pixels per side and 4,194,304 pixels in total. Invalid/unsupported headers and excessive declared dimensions shall not be published as downloaded portraits or passed to the renderer. An unusable contact picture shall fall back to initials. Header checks do not replace codec error handling or bound total decoder memory.

> `zmala_terminal/tests/contact_presence_ui.py`
> `zmala_terminal/tests/test_render_cache.py`
> `zmala_terminal/tests/render_cache_ui.py`
> `zmala_terminal/tests/test_image_bounds.py`

*Parent links:* [ZMC003 Accessible physical controls](product_requirements.md#ZMC003)

<a id="TERM003"></a>

## 3.0 Contact availability _(TERM003)_

Carousel contacts shall show a large green check/Online or red cross/Offline band. Presence shall refresh every two seconds independently of configuration version and show a registered phone becoming unresponsive within 15 seconds, using the server's active reachability result. Contacts shall become unavailable after six seconds without a server update. Offline contacts shall not be dialled.

> `zmala_terminal/tests/contact_presence_ui.py`

*Parent links:* [ZMC003 Accessible physical controls](product_requirements.md#ZMC003)

<a id="TERM004"></a>

## 4.0 Call confirmation _(TERM004)_

The first distinct GREEN press for an online contact shall open their picture and a localized question using their display name: Do you want to call XXX? A second distinct GREEN press shall immediately start the call only after a fresh permission and availability check. Any other key shall cancel and preserve carousel selection; holding GREEN shall not confirm.

> `zmala_terminal/tests/call_feedback_ui.py`

*Parent links:* [ZMC003 Accessible physical controls](product_requirements.md#ZMC003)

<a id="TERM005"></a>

## 5.0 Physical-button prompts _(TERM005)_

Call and callback confirmation shall show large green Yes/check and red No/cross prompts. The prompts shall match the physical buttons, fit at 900 by 620 pixels and remain non-clickable.

> `zmala_terminal/tests/call_feedback_ui.py`

*Parent links:* [ZMC003 Accessible physical controls](product_requirements.md#ZMC003)

<a id="TERM006"></a>

## 6.0 Callback confirmation _(TERM006)_

The first GREEN press for an unavailable contact shall show their picture, name, a red Currently unavailable message and the localized question Do you want to request a callback? A second GREEN shall immediately submit the request. Any other key shall cancel. Submission shall hide Yes/No; success acknowledgment shall appear only after server confirmation.
A pending outgoing request shall show a return-arrow tag on its contact, without persistent callback text beneath the contact name. RED on that contact shall open cancellation confirmation, with GREEN confirming and RED keeping the request. GREEN on an unavailable contact with a pending request shall also offer cancellation instead of another request; GREEN on an available contact shall retain normal calling. A successful cancellation shall remove the tag; failures shall retain it. Polling shall update tags independently of configuration version, without a poll started before a successful mutation undoing its result. Late responses shall not interrupt incoming calls.

> `zmala_terminal/tests/callbacks_live.py`
> `zmala_terminal/tests/test_callbacks.py`

*Parent links:* [ZMC007 Callback requests](product_requirements.md#ZMC007)

<a id="TERM007"></a>

## 7.0 Incoming calls and auto-answer _(TERM007)_

The terminal shall accept incoming calls only from permitted contacts in the configured domain with a valid server proof. Incoming ringing shall show the caller, animated halos, a pulsing portrait border and a phone symbol. GREEN shall answer and RED shall decline. Terminal auto-answer shall apply only when enabled and its countdown shall be cancellable.

> `zmala_terminal/tests/test_terminal.py`

*Parent links:* [ZMC004 Audio and video calls](product_requirements.md#ZMC004)

<a id="TERM008"></a>

## 8.0 Active call controls _(TERM008)_

The terminal shall show incoming video during connected calls, allow RED to hang up and ignore carousel navigation during a call. Late call events shall not reverse a requested hang-up or affect another call.

> `zmala_terminal/tests/accounts_live.py`

*Parent links:* [ZMC004 Audio and video calls](product_requirements.md#ZMC004)

<a id="TERM009"></a>

## 9.0 Missing remote video _(TERM009)_

Connected calls without decoded incoming video shall show No video from the other person and You can still talk while audio and outgoing video continue. A decoded frame shall remove the overlay; four seconds without a frame or disabled negotiated reception shall restore it. New calls shall clear frame history.

> `zmala_terminal/tests/accounts_live.py`

*Parent links:* [ZMC004 Audio and video calls](product_requirements.md#ZMC004)

<a id="TERM010"></a>

## 10 Connectivity indicator _(TERM010)_

The upper-right corner shall show a small terminal-to-Wi-Fi-to-server connectivity graphic using icons, arrows and status colors without text captions. The graphic shall use smooth anti-aliased strokes rendered at the actual display dimensions so the compact symbols remain clear.

The Presenter+ battery icon shall show a lightning bolt when the remote reports an attached charger, including at full charge. Status shall be read off the UI thread and refreshed every five seconds. Unknown, disconnected or stale status shall not imply charging.

> `zmala_terminal/ui/display.py`
> `zmala_terminal/icons.py`

*Parent links:* [ZMC003 Accessible physical controls](product_requirements.md#ZMC003)

<a id="TERM011"></a>

## 11 Caller hang-up while ringing _(TERM011)_

When the caller cancels before the terminal answers, the terminal shall promptly stop ringing, stop ringing animations, cancel any auto-answer countdown and return to the normal carousel.

> `zmala_terminal/tests/callbacks_live.py`

*Parent links:* [ZMC010 Contact notifications and caller cancellation](product_requirements.md#ZMC010)

<a id="TERM012"></a>

## 12 Missed-call badge _(TERM012)_

Each permitted incoming call ended by its caller while the terminal is still ringing shall increase that contact's unread notification count. Its carousel picture shall show a red circular badge with a white handset and a dark counter bubble with a white number. Whenever any uncleared notification exists, the idle screen shall also show this badge in its top-left corner with the combined notification total, including when flagged contacts are visible. Otherwise that corner shall show the ZmalaCall logo. Counts above 99 shall display as 99+ while retaining their exact stored values. Badges shall use smooth anti-aliased graphics with transparent edges to preserve contact pictures. Answered, locally declined and outgoing calls shall not increase counts. Each contact's count shall remain independent.

> `zmala_terminal/tests/test_missed_calls.py`
> `zmala_terminal/tests/call_feedback_ui.py`

*Parent links:* [ZMC010 Contact notifications and caller cancellation](product_requirements.md#ZMC010)

<a id="TERM013"></a>

## 13 Missed-call acknowledgment _(TERM013)_

A contact's entire unread notification count shall clear when GREEN opens their call or callback confirmation, even if confirmation is cancelled and no call is made. A successfully connected incoming call, answered manually or automatically, shall also clear and persist that caller's count immediately. The corner total shall decrease by that count, retaining other contacts' counts. Arrow navigation, configuration refresh, ringing, failed answers and declined incoming calls shall not acknowledge notifications. Repeated connection/media events shall preserve notifications received after connection. New notifications after acknowledgment shall start at one.

> `zmala_terminal/tests/test_missed_calls.py`

*Parent links:* [ZMC010 Contact notifications and caller cancellation](product_requirements.md#ZMC010)

<a id="TERM014"></a>

## 14 Missed-call persistence _(TERM014)_

Unread notification counts shall be saved atomically per local terminal profile and scoped to its SIP account/domain. Counts shall survive restart, be pruned for removed contacts and be erased by factory reset or fresh unconfigured launch. Legacy saved flags without counters shall restore as one notification per flagged contact. Invalid counts or bad saved data shall not prevent startup. Loss of call permission shall count as removal for notification pruning. Re-granting permission shall not resurrect previously pruned counts.

> `zmala_terminal/tests/test_missed_calls.py`
> `zmala_terminal/tests/test_reliability.py`

*Parent links:* [ZMC010 Contact notifications and caller cancellation](product_requirements.md#ZMC010)

<a id="TERM015"></a>

## 15 Manual callback availability notice _(TERM015)_

Configuration polling shall receive pending callback requests independently of configuration version. When both accounts are available, the idle terminal shall select the other person after five seconds without input and show a ten-second availability notice once per request. It shall never automatically dial or interrupt ringing, calls or confirmation.

> `zmala_terminal/tests/call_feedback_ui.py`

*Parent links:* [ZMC007 Callback requests](product_requirements.md#ZMC007)

<a id="TERM016"></a>

## 16 Language application _(TERM016)_

The terminal shall translate its display prompts, availability, questions, Yes/No, callback acknowledgment, video feedback and post-enrollment reset/TV-check messages for all 95 included languages. USB connection, remote pairing/button verification and Wi-Fi/server QR setup shall use English until server enrollment supplies the selected language. Display names shall remain unchanged. Language updates shall apply during calls, with Unicode shaping and right-to-left support; device changes shall wait until idle.

> `zmala_terminal/tests/terminal_languages_ui.py`

*Parent links:* [ZMC006 Terminal languages](product_requirements.md#ZMC006)

<a id="TERM017"></a>

## 17 Factory reset access _(TERM017)_

Reset confirmation shall be accessible only through the Reset entry in local Settings. GREEN shall open the confirmation page, a separate GREEN press shall reset, and RED shall keep configuration and return to Settings. A held GREEN shall not both open and confirm reset. Holding RED on the carousel shall open Settings, never reset directly.

> `zmala_terminal/tests/provisioning_ui.py`

*Parent links:* [ZMC005 Reset and QR setup](product_requirements.md#ZMC005)

<a id="TERM018"></a>

## 18 Factory reset scope _(TERM018)_

Reset shall stop call and maintenance workers and erase the current profile Wi-Fi/server enrollment, configuration cache, button-test verification, TV-check results and missed-call flags. Existing Bluetooth pairing shall remain available, but button verification shall run again. Stale worker responses shall not restore state. Server accounts/groups and other terminal profiles shall remain intact; only application-created Wi-Fi profiles shall be forgotten. Reset shall persist a secret-free Wi-Fi cleanup record before removing the owned Windows or NetworkManager profile. Cleanup failure or restart shall retain and retry that record, and new Wi-Fi enrollment shall wait for successful cleanup. Repeated cleanup shall be idempotent.

> `zmala_terminal/tests/provisioning_ui.py`
> `zmala_terminal/tests/test_reliability.py`

*Parent links:* [ZMC005 Reset and QR setup](product_requirements.md#ZMC005)

<a id="TERM019"></a>

## 19 QR enrollment sequence _(TERM019)_

Pi first startup shall require the camera and verified remote before QR enrollment. Wi-Fi setup shall join the scanned network; existing-link mode shall remain an explicit development alternative. Successful Wi-Fi enrollment shall stop scanning for an unskippable ten-second confirmation, then start server QR scanning. The server QR shall supply the server URL, terminal identity and token; the installer shall not hardcode terminal identity. Authentication and validated configuration shall precede commitment of enrollment. Invalid data, wrong credentials or connection failure shall leave the current step active with an explanation and retry scanning. Installation instructions shall be English until server enrollment sets the selected language. Localized TV-control checks shall follow enrollment before normal use. The Linux preview shall remain contained without obscuring prompts. Reset shall retain the prior language preference for later configured UI, but shall repeat installation checks.

> `zmala_terminal/tests/provisioning_ui.py`

*Parent links:* [ZMC005 Reset and QR setup](product_requirements.md#ZMC005)

<a id="TERM020"></a>

## 20 Stable camera QR scanning _(TERM020)_

QR preview shall be unmirrored and avoid frequent background repaint flicker. QR decoding shall run in an isolated camera worker released before call-engine startup. Worker failure shall show an error border and retry after five seconds; decoded credentials shall not be logged.

> `zmala_terminal/tests/provisioning_ui.py`

*Parent links:* [ZMC005 Reset and QR setup](product_requirements.md#ZMC005)

<a id="TERM021"></a>

## 21 Command execution _(TERM021)_

The terminal shall poll maintenance commands every three seconds, execute one at a time as its desktop or service user in the configured shell from zmala_terminal, and return output, errors and exit status. Commands shall be noninteractive, have bounded output and timeout, and have children stopped on timeout, reset or shutdown. Variables and current directory shall not persist across commands. The retained text shall contain at most 65,536 combined UTF-8 bytes after decoding, including replacement characters. Transient result failures shall retry the same lease without rerunning commands. Permanent result rejection shall attempt a bounded failed-result diagnostic and then resume polling. Linux systemd deployments shall use control-group cleanup; standalone Linux mode only guarantees process-group termination and does not supervise descendants that detach into new sessions.

> `zmala_terminal/tests/test_provisioning.py`
> `zmala_terminal/tests/test_reliability.py`

*Parent links:* [ZMC008 Remote maintenance](product_requirements.md#ZMC008)

<a id="TERM022"></a>

## 22 Interrupted or changed confirmation _(TERM022)_

An allowed incoming call shall interrupt confirmation or request submission without a late response replacing ringing. If a selected contact becomes unavailable, GREEN shall switch call confirmation to callback confirmation and require another GREEN before submission. Cancelling a call preflight check shall prevent late dialing.

> `zmala_terminal/tests/call_feedback_ui.py`

*Parent links:* [ZMC003 Accessible physical controls](product_requirements.md#ZMC003)

<a id="TERM023"></a>

## 23 Text messages use missed-call badges _(TERM023)_

Each new text message from a permitted phone shall increase the same persistent contact notification count as a missed call after validating the server's message proof, sender domain and current receive permission. Duplicate delivery shall not increase counts. Message bodies shall not appear on screen or be saved in badge data. A message received during a call shall retain the call screen and show its badge and counter on return to the carousel. Opening that contact's call or callback confirmation shall clear their entire count even when no call is made.

> `zmala_terminal/tests/test_messages.py`
> `zmala_terminal/tests/callbacks_live.py`

*Parent links:* [ZMC010 Contact notifications and caller cancellation](product_requirements.md#ZMC010)

<a id="TERM024"></a>

## 24 Serial keypad host integration acceptance _(TERM024)_

A future serial keypad adapter shall select a configured stable device port, read without blocking the UI, tolerate Nano startup delay, maintain the protocol heartbeat, reject stale events from a previous connection generation, publish complete lamp snapshots and accept distinct presses without window focus. Disconnect/reconnect, held keys, congestion, startup and reset shall have host integration tests. Firmware simulation alone shall not establish completion. This adapter and physical acceptance remain outstanding; existing terminal controls use keyboard or presenter input.

> `keypad/spec.md`

*Parent links:* [ZMC003 Accessible physical controls](product_requirements.md#ZMC003)

<a id="TERM025"></a>

## 25 Presenter motion volume control _(TERM025)_

On the Linux Presenter+ remote, holding the middle (Pointer) button and moving up/down shall raise/lower C20 playback volume relatively by two percentage points per 64 vertical motion units, within 0–100 percent. Horizontal and unheld motion shall have no action. Release, lost focus or disconnection shall end the gesture. A vertical bar and percentage shall appear at the right while held and disappear two seconds after release; mixer failures shall show an error indication. Motion shall not navigate contacts, place/end calls, change microphone gain or change hardware mute. When the TV is not displaying the terminal UI, the first Pointer press shall only wake the TV and select the terminal input, just like the navigation, GREEN and RED buttons. Motion during that consumed hold shall not change volume; the user shall release and press Pointer again to adjust it. Mixer writes shall run off the UI thread and be limited to ten per second during motion. Local adjustments shall survive core recreation for the app session; an applied change to the server default or an app restart shall restore the configured default.

> `zmala_terminal/platforms/presenter_input.py`
> `zmala_terminal/volume_control.py`
> `zmala_terminal/tests/test_volume_control.py`
> `zmala_terminal/tests/test_presenter_input.py`

*Parent links:* [ZMC003 Accessible physical controls](product_requirements.md#ZMC003)

<a id="TERM026"></a>

## 26 Local settings with remote control _(TERM026)_

Holding RED continuously for ten seconds from the configured carousel shall open local Settings. A progress bar shall appear after two seconds and show elapsed progress toward ten seconds. Early release, another button, lost focus, remote disconnection or an incoming call shall cancel the hold. Repeated key-down events shall neither restart the timer nor repeat actions. Call/ringing RED actions shall remain immediate and shall not start settings access; the second GREEN press shall confirm calls without an added delay. Short idle RED presses shall keep their normal action on release.
Settings shall present a list and an editor side by side. Arrows shall navigate the list, GREEN shall open its editor and RED shall leave settings. Inside an editor, arrows shall change the option or value, GREEN shall accept and RED shall discard the draft. Only the active panel shall show button hints. Connectivity icons shall be hidden; the terminal serial shall appear in small print at the bottom. All labels shall use the selected language.
A Reset entry after the six editable settings shall open the separate localized reset confirmation page without erasing any data. RED on that page shall return to Settings.
Editable settings shall be language, automatic answer (Never, 10 seconds, 30 seconds, 1 minute, 2 minutes, 5 minutes or 10 minutes), automatic framing, speaker volume, three/five portraits and TV return timeout (30 seconds, 1, 2, 5, 10, 20 minutes or Never; default 30 seconds). Accepted changes shall be acknowledged by the server and persisted locally. Failed saves shall retain the editor and show a localized error; server conflicts shall not silently overwrite newer values. Incoming calls shall interrupt settings and discard unconfirmed drafts.

> `zmala_terminal/tests/test_local_settings.py`
> `zmala_terminal/tests/settings_ui.py`
> `zmala_server/tests/device-settings.test.js`

*Parent links:* [ZMC003 Accessible physical controls](product_requirements.md#ZMC003)

<a id="TERM027"></a>

## 27 Remote onboarding and status _(TERM027)_

Pi setup shall wait for the C20, then a paired remote with functioning input. An illustrated test shall require distinct press/release events for left, right, green, red and middle in order, highlighting only the expected button. Successful verification shall be persisted against the pairing identity; disconnection shall reset incomplete progress. Pairing without working input shall not advance setup. Normal UI shall show Bluetooth connection and battery/charging status when available. A missing remote page shall explain switching on and charging without claiming that a disconnection proves the remote is off. Setup illustrations shall identify the rear pairing/power controls and the green/red stickers.

> `zmala_terminal/remote_test.py`
> `zmala_terminal/tests/test_remote_test.py`
> `zmala_terminal/platforms/remote_health.py`

*Parent links:* [ZMC005 Reset and QR setup](product_requirements.md#ZMC005)

<a id="TERM028"></a>

## 28 TV setup and idle restoration _(TERM028)_

After server enrollment, localized TV checks shall ask consent for standby, wait three seconds, wake and request user confirmation. A second test shall wait for a different TV input, then attempt terminal/previous/terminal input selection with two-second intervals and request confirmation. Failures shall offer retry/help, including Samsung network-control guidance. Attempt and result data shall persist and reset shall clear it. When another input or standby is active, the first remote press shall restore the terminal view and consume that press. Browsing inactivity shall restore the captured prior TV state after the configured timeout, default 30 seconds. Every button activity shall reset the countdown; a thin blue bottom bar shall appear only after ten seconds of inactivity. Calls, held buttons, onboarding and pending settings saves shall prevent idle restoration. A stale asynchronous operation shall not restore over a newer TV session.

> `zmala_terminal/tv_check.py`
> `zmala_terminal/tests/test_tv_check.py`
> `zmala_terminal/tests/test_idle_return.py`

*Parent links:* [ZMC003 Accessible physical controls](product_requirements.md#ZMC003)

