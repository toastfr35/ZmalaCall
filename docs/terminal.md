# ZmalaCall terminal implementation

This technical guide covers the shared Python terminal and its Linux/Pi and
Windows adapters. It is for developers and maintainers. Preparation, enrollment
and everyday operation are covered by the release's `ZmalaTerminal-Installation.pdf`
and `ZmalaTerminal-Guide.pdf`. Their editable sources are `terminal_prep.docx`,
`terminal_config.docx` and `terminal_use.docx`.
See [general.md](general.md) for build/network conventions and [server.md](server.md)
for the authenticated configuration and SIP services.

Contents: [purpose and functions](#terminal-purpose-and-functions),
[architecture](#architecture-and-thread-ownership), [deployment](#pi-deployment-pipeline),
[onboarding/reset](#onboarding-and-reset-state), [settings/input](#settings-and-controls),
[remote](#remote-status-and-recovery), [TV/display](#tv-control-and-display),
[media](#video-and-audio), [services](#appliance-services-storage-and-peripherals),
[Windows/rendering](#windowssource-launch-and-architecture), [verification](#verification-and-troubleshooting).

## Terminal purpose and functions

ZmalaCall is a home audio and video call terminal. It connects a television,
a Nuroum C20 camera with a microphone and speaker, and a Microsoft Presenter+
remote to a Raspberry Pi. The television shows the people that the user can call.
The remote lets the user select a person and control the call.

The terminal is intended for people who need simple controls, including elderly
users. It provides a small set of actions with clear visual feedback. The user
does not need a keyboard, a mouse or a web browser for normal operation.

The server supplies the terminal identity, permitted contacts and settings. The
terminal controls its own display, devices and calls. It reports its state to the
server and sends accepted local setting changes back to the server.

This description covers the Pi terminal with its software already installed.
Software packaging and installation are outside this description. Server functions
are described only where they form an interface with the terminal.

### 1. Startup and shutdown

The terminal starts automatically when the Pi starts. It opens the application
across the television screen. It resumes initial setup when setup is incomplete.
Otherwise, it loads the saved identity and settings and starts normal operation.

The terminal can start when the server is unavailable. It shows the available
local state and tries to reconnect. A service supervisor restarts a failed
application. Shutdown stops the work and devices owned by the application.

### 2. Initial setup and reset

Initial setup guides the user through camera connection and remote pairing. A
button test confirms that the remote works before setup continues. The camera
reads a Wi-Fi code and a server code. The server code supplies the terminal
identity and access credentials.

Setup shows an error when an operation fails. It continues only when that step
has completed. TV tests follow server registration and use the selected language.
The user can reset the terminal from Settings after a separate confirmation.
Reset removes this terminal profile's setup data but does not delete server accounts.

### 3. Network connection

The terminal uses Ethernet or Wi-Fi to reach the server. Initial setup configures
Wi-Fi from the scanned code. The terminal keeps that connection for later use.
The Wi-Fi indicator shows wireless status even when server traffic uses Ethernet.

A connection failure does not close the application. The terminal detects the
failure, reports the available status and retries communication. Reset removes
only the Wi-Fi profile that the terminal created.

### 4. Server communication

The terminal uses its assigned credentials to communicate with the server. It
receives its permitted contacts, settings, contact availability and callback state.
It sends its operating status and the results of user or maintenance actions.

The terminal checks received data before it uses that data. Invalid or old data
does not replace newer accepted settings. Background communication does not wait
for portrait downloads. A late response cannot replace state from a newer operation.

### 5. Configuration

All terminal volume UI uses 5% steps, including Settings, the middle-button volume page and the server terminal editor. Left/right on the volume page moves an existing between-step level to the next boundary in the chosen direction. The speaker-volume editor uses 5% steps. Existing values between steps open at the nearest step and stay unchanged until accepted.

The ringtone editor wraps at both ends: left on the first choice selects the last, and right on the last selects the first, without saving.

Red on the Settings list asks whether to exit: green confirms; red keeps the same list selection. Red within an editor only discards that draft. Neither exit answer changes saved configuration.

The eight-row Settings menu reserves a full text line for each label and saved value at both supported sizes; short values such as Nokia and the speaker percentage remain complete.

The server supplies the main terminal configuration. The local Settings page lets
the user change language, automatic answer, framing, speaker volume, ringtone, portrait count
and the return-to-TV timeout. Each editor lets the user accept or cancel a change.

The terminal confirms a saved change only after the server accepts it. A rejected
or failed change produces visible feedback. Settings that require a new media
configuration wait until the terminal is idle. Supported live changes do not end a call.

### 6. Remote control

The remote has left, right, green, red and middle controls. Green and red stickers
identify the two action buttons. Button actions depend on the current page or call
state. Pressing the middle button opens a dedicated volume page; left/right changes volume and a second middle press closes it.

The terminal detects remote connection, battery level and external charging power
where the device reports them. It shows help when the remote is unavailable.
A lost connection alone cannot show whether the remote is off, discharged or faulty.

### 7. Contact selection and navigation

The user moves left or right through the permitted contact list. Each contact has
a portrait, name and availability indication. The selected contact remains selected
when a compatible directory update arrives. Offline contacts remain available for
callback requests.

The same controls navigate settings and confirmation pages. Green selects or
accepts an action. Red cancels or returns where the current page permits it.
Incoming calls take priority over unfinished navigation and edits.

### 8. User interface and language

The display uses large portraits, clear text and consistent action colors. Names
stay inside their portrait cards. The settled centre card uses a larger, bold name
to emphasize the selected person; long names shrink to fit above availability.
Moving cards retain the compact name style until navigation settles.
Status symbols and words give information without
relying on color alone. Confirmation pages make the proposed action clear.

Normal operation uses the selected language. Early setup uses English before the
server supplies that preference. Text rendering supports Unicode names and scripts.
Missing pictures or translations use the defined fallback presentation.

### 9. Call control

The user confirms an outgoing call before the terminal starts it. The terminal
checks contact availability and permission again at confirmation. Incoming calls
require an authorized caller. The user can answer or decline them.
The terminal handles one active call at a time and declines a second incoming call.

Automatic answering is optional and includes a visible delay. The user can decline
a call during that delay. Red ends a connected call. Cancellation, failure and
normal call completion return the terminal to the appropriate idle state.

### 10. Audio

The terminal uses the C20 microphone and speaker for calls. It plays an incoming
ringtone and an outgoing waiting tone on the C20 speaker. Speaker volume can
change without changing microphone gain or television volume.

Audio processing provides the configured echo-control behavior. The Pi waits for
all C20 media instead of starting a receive-only call or selecting TV audio.
Missing devices or rejected routes retry once per second while SIP and remote
buttons remain responsive. A cancelled or superseded call cannot resume.
USB wake restores the requested speaker level before media is ready.

### 11. Video

The terminal sends camera video and displays received video. A small local preview
lets the user see the outgoing camera view. The local preview shares the camera
capture path with the outgoing stream.

Video size and frame rate are configurable targets. Actual delivery depends on
the camera, processing capacity and network. Before the first remote picture,
the call page shows a neutral video-starting message and an unslashed camera
icon for eight seconds. A decoded picture clears it immediately; if none arrives,
the page changes to missing-video feedback while preserving audio and the local
preview. Once video has appeared, a subsequent four-second stall uses the
missing-video message without another startup grace period. Each new call resets
the initial wait. Both message phases use the selected language.
Optional local people detection adjusts the frame
within a two-times digital zoom limit. Detector failure restores the wide view.

### 12. Call history and callback requests

The terminal keeps unread counts for missed incoming calls and authorized phone
text notifications. It shows these counts beside the relevant contacts and in a
total indicator. It does not display or save the text bodies.

The user can request a callback from an unavailable contact and cancel a pending
request. A contact tag shows the pending request. When the contact becomes
available, the terminal can notify the user. It does not dial automatically.

### 13. TV control

The terminal tests TV power and input switching during setup. The user confirms
the observed result of each test. Confirmed capabilities control later automatic
TV actions. Failed or skipped capabilities remain available through manual TV control.

When the TV hides the terminal view, the first remote action can reveal that view.
That action does not also operate the terminal page. The terminal remembers the
observed previous TV state and restores it after the relevant call or idle timeout.
A bottom progress bar shows the approaching idle return.

### 14. Connected devices and power

The terminal detects required media devices and uses their identities after
reconnection. It controls the supported case fan during connected calls. Device
work that can block runs separately from display updates.

Optional USB power control can turn off the shared camera and charger supply
when the terminal is inactive and the remote battery has sufficient charge.
User activity or an incoming call requests power restoration. Unknown device or
battery state favors retaining power. The webcam indicator reports confirmed hub power.

### 15. Maintenance and diagnostics

The terminal reports application, connection and media status to the server.
Authorized maintenance jobs run with limited duration and output. Cancellation,
reset and shutdown stop work that belongs to the terminal.

Routine logs use volatile storage to limit microSD writes. Temporary detailed
logging helps diagnose failures. Diagnostics protect credentials and distinguish
reported device state from unverified sound or picture quality.

### Qualities that apply to all functions

The terminal favors simple, predictable interaction. User messages explain the
current state and the next available action. The same terms and controls keep
the same meaning throughout related pages.

The terminal protects saved identity and settings and rejects invalid updates.
It separates background work from display and call control. It limits retained
queues, pictures and logs. Recovery behavior preserves newer state when old work
finishes late.

Access controls protect calls, server requests and maintenance actions. Stored
credentials remain private. Camera images used for framing stay on the terminal.
Automatic TV control and hardware performance require tests on the actual equipment.

The HLRs below this description's functional structure define observable product
responsibilities. The LLRs define settings, limits, state transitions and interface
rules. Code and tests trace to those LLRs; test links alone do not establish a pass.

## Architecture and thread ownership

The shared UI, models, enrollment and call logic live in `common/`. The `windows/`
and `linux/` directories provide platform rendering, network, process and native
media adapters. The common entry point is `python -m zmala_terminal.common.main`.
Linux source archives exclude Windows adapters and locally built native artifacts.

| Shared modules (under `common/`) | Responsibility |
| --- | --- |
| `main.py` | Own state/resource lifetimes and compose controllers |
| `input_control.py`, `settings_control.py`, `idle_return.py` | Input/repeat handling, drafts/hold and TV timeout |
| `model.py`, `call_control.py`, `management.py` | Call/notification state, async actions, polling and timers |
| `configuration.py`, `config_validation.py`, `configuration_control.py` | HTTP validation/cache and idle engine replacement |
| `setup_flow.py`, `provisioning.py`, `remote_test.py`, `tv_check.py` | Enrollment/reset and persisted setup verification |
| `ui/`, `theme.py`, `icons.py`, `text_renderer.py` | Display, confirmation, carousel and platform rendering |
| `engine.py`, `linphone_api.py`, `native_runtime.py` | Shared native ABI/call engine and platform loading |
| `qr_scanner.py`, `qr_worker.py`, `native_qr.py` | Isolated camera process and preview protocol |
| `maintenance.py`, `process_job.py`, `volume_control.py` | Command ownership, process cleanup and mixer worker |

`Terminal` owns shared state; controllers do not keep independent state copies.
Tk and core iteration run on the UI thread. Native media owns worker/ticker
threads; HTTP/Wi-Fi results return through queues. Generation/serial checks discard
late results after reset, cancellation or replacement. Native callbacks/DLL handles
remain referenced until their core closes; borrowed call pointers are explicitly
retained/released. Shutdown is idempotent, though SDK/QR waits can still block.

Configuration polls and settings responses share validation, rollback rejection
and stable-cache policy; presence/callback fields are not persisted every poll.
Malformed contact photo values are rejected as configuration validation errors
before path matching or image loading.
Authenticated HTTP rejects redirects. Failed engine setup retains the newest
desired configuration for idle retry after five seconds, without publishing it as
successfully applied. QR capture is isolated from native decoder failure and
releases the camera before the call engine acquires it.

## Pi deployment pipeline

`build_tools/windows_installer/` embeds the Python/SSH client and a checksummed
source archive. Both Tk and headless entry points use the same backend. Preflight
validates Raspberry Pi OS Lite 64-bit Debian 13 Trixie, Pi 4 Model B, hostname,
sudo access, boot mount, disk space and a physical Ethernet route. Factory
hostname/account defaults are `zmala.local` and `zmala`, with the initial password
matching the account name. The account/device identity is supplied later by QR.

`windows_installer/ssh_transport.py` supplies the shared SSH transport and job
monitor; the terminal backend owns its validation, upload and reboot checks.
SSH host-key pinning and a retained Ethernet IP prevent mDNS changes from moving
the deployment to another connection. A separate systemd install job survives a
PC connection loss. The shell install runner serializes installation, records
stage failures and prepares root-owned releases before switching `current`.
The backend verifies a new boot ID and stable services after reboot. A successful
install establishes startup health, not physical audio/video or enrollment acceptance.

The standard Windows installer enables Argon fan configuration. USB power switching
remains an explicit experiment. Pi install logs are under `/var/log/zmalacall-install/`;
PC logs are under `%LOCALAPPDATA%\ZmalaCall\Installer\logs`. Updates preserve private
state. Failure after OS/package changes is not a transactional system rollback.

### Headless mode and local build

The same executable supports unattended deployment, including reboot:

```powershell
$setup = Start-Process -FilePath .\ZmalaTerminal-Pi4-setup.exe `
    -ArgumentList '--headless', '--host', 'zmala.local', '--yes', `
                  '--log', 'C:\Temp\zmala-install.log' `
    -Wait -PassThru
$setup.ExitCode
```

Use `--check-only` instead of `--yes` for a read-only preflight. The GUI executable
needs explicit waiting in scripts. Exit codes: 0 success, 1 check/install/log
failure, 2 invalid arguments or missing consent, 130 interrupted. Without `--log`,
headless logs use the normal installer log directory. Interruption may leave the
Pi job running. QR and physical remote/TV setup still follow on the terminal.

To build on Windows with a Tk-enabled Python:

```sh
python -m pip install -r build_tools/windows_installer/requirements.txt
python build_tools/windows_installer/build.py
```

Output is `build_tools/dist/ZmalaTerminal-Pi4-setup.exe`; CI builds/smoke-tests the
same unsigned executable in GUI/headless modes. Installer downloads include the
two terminal PDFs rendered from the retained Word sources and illustrations.

### Manual package installation

From the source checkout on the PC:

```sh
python build_tools/linux/package-terminal.py
scp build_tools/dist/ZmalaCall-Terminal-rpi.tar.gz* zmala@zmala.local:~/
```

Over Ethernet on the Pi:

```sh
sha256sum --check ZmalaCall-Terminal-rpi.tar.gz.sha256
mkdir -p ~/zmala-install
tar -xzf ~/ZmalaCall-Terminal-rpi.tar.gz -C ~/zmala-install
cd ~/zmala-install
sudo ./install.sh --argon-one
sudo reboot
```

Unlike the Windows executable, the shell installer uses `--argon-one` explicitly
for the case. It verifies the archive manifest, physical Ethernet, boot mount,
3 GiB free on `/var` and 128 MiB on `/boot/firmware`; failures identify the stage
and return nonzero. Dependency download failures are fatal. Retrying preserves
enrollment; OS/package changes are not automatically rolled back.

| Shell option | Purpose |
| --- | --- |
| `--user zmala` | Non-root service user; default is `zmala` |
| `--ssh-interface eth0` | Physical wired interface for SSH |
| `--display-mode 1280x720` | Default HDMI desktop; `1920x1080` or `auto` are alternatives |
| `--no-splash` | Leave boot presentation unchanged |
| `--without-framing` | Skip detector installation; leave framing disabled |
| `--data-from PATH` | Explicit migration of missing old state |
| `--bootstrap PATH` | Administrator-supplied connection JSON instead of server QR |
| `--wifi-mode existing-link` | Development-only bypass of joining the scanned Wi-Fi |

Use the system Python on Pi: apt-installed GI, Cairo, Tk and OpenCV are not
automatically visible in a pip virtual environment. The installer supplies Xorg,
Openbox, Picom, BlueZ, NetworkManager, Liblinphone 5.3, native media plugins,
framing runtime/model and fonts. Linux packages include shared/Linux source only.

## Onboarding and reset state

`setup_flow.py` coordinates USB readiness, pairing/button verification, Wi-Fi QR,
server QR and post-enrollment TV checks. `provisioning.py` persists accepted
identity and owns reset cleanup; `qr_scanner.py` owns a separate camera process.
The Linux preview releases partially acquired decoder, window and X11 resources
if embedding or capture initialization fails; closing it is idempotent. The parent
ignores malformed JSON and non-object pipe messages before dispatching QR strings.
The application entry function keeps CLI parsing and final cleanup testable without
starting a real kiosk.
Each asynchronous completion is checked against the current setup generation.

| Stage | Advancement condition and retained state |
| --- | --- |
| USB readiness | C20 detected; charger is power-only and cannot itself be detected |
| Pairing | A unique advertising Presenter+ with HID service; BlueZ pairing alone is insufficient |
| Button verification | Distinct physical left/right/green/red/middle press and release sequence, saved against pairing identity |
| Wi-Fi QR | Actual join succeeds, followed by an unskippable ten-second confirmation; existing-link is a development mode |
| Server QR | URL, device ID and token decode; authenticated, validated configuration succeeds before committing enrollment |
| TV checks | Independent power/input outcomes and TV binding persist before normal use |

Before enrollment, prompts use English. Enrollment applies the selected language;
detailed diagnostic catalogs use English fallback where a translation is absent.
Invalid codes, unreachable servers and rejected credentials retain the current
stage with retry feedback. Both QR stages show mint corner guides with a dark
outline around a centred square in the unmirrored camera picture. Hold the whole
code inside the guides; the centre stays clear. Guides resize with the displayed
picture, including letterboxing, and are added only to its display copy: decoding
still receives the entire untouched camera frame. QR preview remains contained
within the screen and its process releases the camera before call-engine startup.

Reset is entered through Settings with a separate confirmation. It invalidates
workers and clears the current profile's enrollment, configuration cache, missed
counts, button verification and TV results. Existing Bluetooth pairing remains,
but the button test repeats. Only application-owned Wi-Fi profiles are removed.
A secret-free cleanup record survives failures/reboot; cleanup retries block new
Wi-Fi enrollment. Other profiles and server accounts are unaffected.

The device ID is supplied by the server QR and is independent of hostname or
hardware serial. New physical hardware needs its own Bluetooth and Samsung
permissions even when it reuses an account enrollment. Wi-Fi status is sampled
independently of the Ethernet path used to reach the server.

## Settings and controls

`input_control.py` maps keyboard and physical reports to model actions.
`settings_control.py` owns drafts and the long-red gesture; `volume_control.py`
coalesces mixer work. The following mappings are implementation behavior, while
`terminal_use.docx` explains the caller workflow.

| Control | Action |
| --- | --- |
| Left/right | Select contacts; navigate settings/options or change a value |
| Green | Open confirmation, call/request/answer, open a setting or accept its draft |
| Red | Cancel/decline/end, cancel a selected callback request, or discard/leave an editor |
| Hold red for 7 seconds on the carousel | Open Settings; progress appears after two seconds |
| Press middle | Open/close the dedicated horizontal volume page |
| Left/right while volume is open | Decrease/increase speaker volume in 5% steps |

Windows equivalents are Left/Right, Enter and Escape. F11 toggles fullscreen
outside confirmation. Button repeat cannot confirm a call; release, another
button, focus loss, disconnect or an incoming call cancels the settings hold.
The Presenter green sticker covers the microphone button; red covers Teams.
Middle is Pointer. Remote motion is ignored for volume. While the volume page is open, buttons do not navigate contacts, dial, hang up or open Settings. Call/state changes and setup/focus changes dismiss the page; an existing call continues.

Settings has a list and editor; only the active side shows button hints, status
icons are hidden, and the terminal serial appears at the bottom. Confirmed edits
go back to the server. Failed/conflicting saves retain visible error guidance.
After reconciliation, retry expectations use the editor defaults for optional
fields omitted by older valid configurations.
The label renderer reduces the font to fit each settings region. If a long
translation still wraps beyond the region, it uses an ellipsis and keeps
combining marks with their preceding character. This also keeps the button hints
inside the small-window layout.

| Setting | Local choices |
| --- | --- |
| Language | Server-supported languages |
| Automatic answer | Never, 10 seconds, 30 seconds, 1, 2, 5 or 10 minutes |
| Automatic framing | On/off; Pi C20 only |
| Speaker volume | 0–100%, in 5% steps |
| Ringtone | Nokia (default) and the private server library |
| Portraits | Three/five; short contact lists retain three positions |
| Return to TV | 30 seconds (default), 1, 2, 5, 10, 20 minutes, Never |
| Reset | Confirmed local reset and re-enrollment |

Open Ringtone with green, then use left/right to hear the highlighted choice.
Preview starts after 400 ms without another selection and plays for at most ten
seconds through the C20 at the current speaker volume. It waits for a waking C20;
zero volume remains silent. Green saves the choice after server acknowledgement;
red cancels it. Leaving the editor or receiving a call stops preview immediately.
The editor shows waiting, playing, muted or playback-failure feedback.

`ringtones.py` downloads selected private audio asynchronously from the enrolled
origin with terminal authentication, validates its canonical SHA-256 path and
normalized PCM bytes, and atomically caches it under the profile's data folder.
The catalog holds Nokia plus at most 64 private choices. Each custom WAV is mono
16-bit PCM at 16 kHz and at most 30 seconds. Valid cached audio works offline;
incoming calls use Nokia until a selected download becomes available. Reset
cancels pending cache writes. `usb_power.py` owns bounded C20 preview playback,
including installations without USB power switching; incoming ringing preempts it.

Outside calls the volume page covers the UI with one centered horizontal control,
direction icons and the current percentage. During a connected call it becomes a
compact overlay above the video, leaving most of the picture visible. Press middle to open it, click left/right for
5% steps, and press middle again to close it. Button release does not close it,
and it has no automatic timeout. A red exclamation indicates mixer failure.
It changes speaker/ringtone playback, not microphone gain/mute. Mixer requests
coalesce on one worker at at most ten per second, with a final pending value
flushed on closing. Volume changes survive calls/core replacement in the current
session; restart or a changed server volume restores the saved setting.

Contact names stay within portrait frames. Online/offline bands use symbols and
words. Green opens a separate call confirmation for an online contact or callback
confirmation for an offline contact; another distinct green press confirms.
Availability is checked again before dialing. Offline contacts stay visible.
Incoming calls interrupt drafts/confirmation without late callbacks overwriting
the ringing screen. Connected calls show remote video and a bottom-right self-view.
Missing remote video shows an explanation without stopping audio/outgoing video.

Pending callbacks have a separate return-arrow badge. Red opens cancellation
confirmation. Requests update only after acknowledgement, and stale polls cannot
restore a cancelled request. Eligible callback contacts may be selected after an
idle interval, but still need call confirmation; there is no automatic callback dial.

Missed incoming calls and authenticated phone texts share per-contact unread
counts. Merely browsing preserves them; opening that contact's confirmation clears
its count, even when cancelled. Connecting an incoming call also clears its count.
Answered/locally declined/outgoing calls do not create missed counts. Bodies are
not displayed or stored. Counts persist by SIP account/domain and are pruned for
removed/ineligible contacts. The corner badge totals them; values over 99 display
as `99+` while exact counts remain stored.

## Remote status and recovery

Bluetooth is green when Presenter input devices are open, red/slashed when
unavailable, grey where monitoring is unsupported (including Windows). The idle
recovery page appears after five seconds without input availability and clears
automatically on recovery; it does not wake the TV or supersede a call.
Background checks distinguish absent pairing, disabled adapter, blocked device
and connected-but-unready input. A disconnected remote cannot be reliably
classified as switched off, out of range, flat or faulty; the help explains
switching it on and charging it.

Battery is green above 20%, amber at 11–20%, red at 0–10%, and unknown if stale
or unavailable. Five-second checks expire after 20 seconds without an update.
The lightning bolt uses the Presenter's measured charger-connection HID report;
it indicates external power, including at full charge, not measured charging current.
Unsupported report shapes remain unknown.

For manual pairing recovery, stop `zmalacall-pairing` to avoid competing agents.
Unblock Bluetooth with `sudo rfkill unblock bluetooth` if needed, start
`bluetoothctl --agent NoInputNoOutput`, select `default-agent`, `power on` and
`scan on`, then pair/trust/connect the currently advertised Presenter address.
Keep the agent running until completion; stop discovery and restart the pairing
service afterward. A pairing-mode address can change. Moving an SD card to a
different Pi does not transfer the Bluetooth controller identity.

## TV control and display

The first mapped button when TV power/input hides the UI wakes/selects the
terminal and is consumed, as are presses while HDMI settles. It cannot also dial
or change contacts. This includes the first middle/Pointer press: that consumed
press does not open volume. Release and press again to open the volume page.
With no CEC, normal button behavior remains available; unknown routing limits
detection.
After restart, a missing power observation still permits a previously qualified
power-on, even if the separate source-switching check was skipped or failed.
The first press configures the CEC playback identity if needed and wakes the TV;
it remains consumed. Unknown power is never saved as a standby restoration target.
If power control was not qualified, an unknown state cannot authorize waking it.

Incoming calls remember observed power/source before revealing the UI. Decline,
caller cancellation or hangup restores that state. Browsing has its own return
timeout: button activity resets it, a thin blue bar appears after ten seconds
idle, and expiry restores the captured state. Calls and pending saves suspend
the timer. Volume/mute are not changed by CEC. Unknown previous input is not guessed.

### Installation TV checks

After server enrollment the wizard pauses media startup and idle restoration.
Green starts the standby/wake test; a three-second off interval follows a bounded
standby-report wait. The user confirms whether the picture went off and returned.
For input testing, switch to another channel/input with the TV remote. The wizard
detects departure, returns to ZmalaCall, restores the previous source, then returns
again, allowing three seconds between commands. Select the input manually if it
does not return within 30 seconds. Green confirms success; red offers recovery/retry
or manual operation. CEC acknowledgements alone do not count as a pass.

`/var/lib/zmalacall/<profile>/tv-check.json` stores attempts, performed/results/
skips, completion, EDID hash and HDMI address. Save failures block completion.
Interrupted tests resume at a prompt, not another automatic power command.
A changed TV/route invalidates previous results on startup; reset clears them.
Failed/skipped features are disabled independently; keep the TV remote available.

Samsung recovery covers Anynet+/Network Control, local discovery and permission
approval. The user selects among discovered TVs. The fallback stores private
`tv-remote.json` credentials with mode 600 and a pinned TLS certificate, and sends
`KEY_TV` for the remembered tuner source. A power-toggle fallback is used only
after rechecking a settled on-state, never for unknown/transitional/off status.
It does not restore arbitrary smart-TV apps.

Some Samsung models need a verified HDMI key bound to their actual physical
address, for example `"terminal_source":{"address":"1.0.0.0","key":"KEY_HDMI"}`.
The wizard saves it only after the user confirms the complete round trip.
`KEY_HDMI1` and `KEY_HDMI` are not interchangeable on every model. Cable moves
invalidate the binding; changed TV address/certificate requires pairing again.
For manual recovery, run `build_tools/linux/pair-samsung-tv.py <TV-IP>` as the
terminal service user and approve the TV prompt. Removing the private credential
file disables network fallback without removing CEC.

Sony BRAVIA uses standard CEC, not Samsung commands. Enable BRAVIA Sync control
and TV auto power on, and check its device list under External inputs (menu names
vary). Older models call this Control for HDMI/HDMI CEC. Physical BRAVIA operation,
especially tuner restoration, has not been qualified; use the wizard's actual
picture checks rather than assuming protocol support guarantees switching.

### HDMI presentation

HDMI desktop resolution is independent of transmitted call resolution. The kiosk
defaults to 1280×720 near 60 Hz when advertised, avoiding a 4K desktop; the shell
installer can select 1080p or auto. Plymouth displays the logo/family word cloud;
firmware/HDMI negotiation may still produce brief blank screens. Original boot
files are saved as `*.before-zmala`; rescue consoles remain on other VTs.

The kiosk owns display `:0`/VT7 and disables a competing desktop display manager.
Picom uses XRender/VSync with fullscreen composition. Supported Pi 4 Xorg drivers
receive the `msdri3` override in `/etc/X11/xorg.conf.d/21-zmalacall-pi4.conf` to
permit synchronized page flips; Tk buffering alone did not prevent scanout tearing.
The override is board/driver-specific. The Xorg 21.1 driver does not implement
the newer `TearFree` option. Carousel animation uses absolute 60 Hz deadlines,
skipping missed deadlines; this is not a guaranteed 60 fps rendering rate.

CEC adapter selection prefers connected EDID-bearing outputs, then enabled
scanout, retaining the current adapter when disconnected for standby wake.
An explicit observer `--device` stays fixed; saved restoration is not redirected
mid-call. Check TV input, cable, EDID, display service and observer selection before
forcing HDMI boot modes. A fresh supported image is preferable to Pi 3 migration
settings, which can retain obsolete display and Bluetooth configuration.

## Video and audio

Fresh profiles use 720p at 15 fps. Each terminal independently selects 480p
(640×480), 720p (1280×720) or 1080p (1920×1080), with 10/15/20/25/30 fps targets.
Legacy 360p maps to supported 480p. Media graph changes wait until idle;
framing and speaker volume have live controls.

| Resolution | Upload budget at 15 fps (kbit/s) | Receive allowance (kbit/s) |
| --- | ---: | ---: |
| 480p | 700 | 2000 |
| 720p | 1500 | 4000 |
| 1080p | 2500 | 6000 |

Upload is `ceil(base × target_fps / 15)`; receive allowance is independent of the
local FPS to support a faster peer. These are SDK bandwidth allowances, not
reserved network bandwidth or guaranteed quality. Camera exposure, scene detail,
codec/UI work and network jitter affect delivered frames. Read actual capture,
negotiated and decoded dimensions/rates, not just configuration or transmit counters.

Linux uses explicit C20 MJPEG capture, Pi `bcm2835-codec` H.264 encoding and
FFmpeg software H.264 decoding. It does not silently choose another camera or
HDMI audio when the C20 is absent. Camera format/size checks avoid the SDK's
YUYV/VGA fallback. The admin page offers no camera, microphone or speaker selector for the Pi.
Legacy Windows compatibility retains SDK devices and H.264/VP8;
its local OpenH264 receive adapter preserves valid NAL bytes that the bundled
adapter corrupted. Pi peers use H.264. Hardware decoding is not the current path.

Capture keeps the latest pending frame. JPEG decode, framing and preview reduction
run on a separate worker with one waiting JPEG and one completed picture. The
H.264 decoder uses two threads and ordered compressed queues; arbitrary compressed
frame dropping would corrupt references. Encoding reuses buffers and scales only
when input/target sizes differ. Encoder overflow recovers with fresh headers;
recovery requests are coalesced. Queue count/age diagnostics exist; byte budgets
and bounded stuck-native shutdown remain outstanding.
When a damaged received access unit is discarded, its received SPS/PPS NALs
remain cached and precede the next intact unit. Discarding those setup NALs as
well can leave every later frame undecodable after an initial loss over a relay.
The native filter regression checks this recovery without submitting damaged
slices to the decoder worker.
Before the first decoded picture, the receiver also requests a keyframe once per
second. Waiting only for decoder errors can leave it stuck after ICE drops the
initial setup frame: accepting later inter frames need not report a fresh error.
Retries stop after a decoded picture and resume if the first-picture notification
is reset during a stream update.
The pinned TURN correction also retries TLS short writes and socket backpressure
through the shared `common/native/turn-write.h` helper. It polls in 100 ms steps
and shuts down the connection if a frame cannot finish within three seconds.
This avoids dropping the middle of large keyframes when the SDK's small socket
send buffer fills. The native TURN regression exercises exact output bytes,
retry buffer identity, timeout and closed/error paths.
The Pi correction also reads the actual operating-system socket error in the
TLS callbacks. The pinned SDK instead negates `send`/`recv`'s `-1` result and
mistakes temporary backpressure for a disconnected peer. Under video load that
can close the video relay connection while the separate audio connection survives.
`T-LLT-080` fills a real local socket buffer to EAGAIN, checks read/write retries
and peer closure, and fails against the original SDK callbacks before passing
against the correction. TLS verification and the three-second write bound remain.

The local preview shares camera capture, averages pixels before final display
scaling and uses NEON for common 2×/4× reductions with scalar fallback. Small
frames avoid another reduction copy. Drawing occurs for new frames/state changes
plus a 250 ms recovery refresh, rather than every empty ticker pass.
Current short Pi 4 checks established two-way 1080p20 when the peer camera exposure
could supply 20 fps; they do not qualify sustained 30 fps or uniformly low latency.
An old 15 fps observation is not a hard limit. Low-light exposure can limit capture
below its advertised format rate; a faster server does not fix that bottleneck.

C20 routing uses both core default audio-device objects and the pending call's
input/output objects, with readback validation. This matters when an incoming
call is created while USB is off: changing only core defaults leaves that call's
old HDMI route intact. Native references remain owned until all setters/readbacks
finish, then are released. Dial/answer refresh the devices before allocating call
parameters. Setup also retries missing C20 hardware after one second (other
engine failures retain the five-second retry).

On 19 October 2026, `tests/terminal/HLT/c20_audio_native.py` passed on term2
with its installed Debian SDK: a loopback incoming call initially selected HDMI,
then reported C20 input and output after rebinding and reaching StreamsRunning.
This checks native route selection; physical listening and USB wake timing are
separate checks. Run this opt-in test only with the terminal service stopped and
the C20 powered on; it uses temporary SDK data, no account credentials, external
peer or recording, and releases both cores afterwards.

C20 microphone input is 16 kHz stereo; playback is 48 kHz stereo. The speech
profile limits echo processing to the native input rate while retaining the
48 kHz Opus clock and playback resampling. Normal processing remains selectable.
Before loading Liblinphone, the Pi adapter selects the process-local
`linux/media/audio/c20-alsa.conf` policy. It retains the distribution configuration
for other cards and replaces only the Nuroum C20 default PCM with separate
capture/playback converters to its hardware rates and stereo S16_LE format.
The supplied ALSA card identity is retained, including after USB renumbering.
This avoids generic `dsnoop` opening the C20 input at its default 48 kHz and
keeps ringback/call conversion in software. Missing policy prevents SDK startup
with an explicit installation diagnostic. The real ALSA parser regression
expands both directions without opening hardware.
Echo cancellation uses a 500 ms window/automatic delay; assess real speech before
changing it. Packet counters alone do not establish intelligibility or acoustic
echo performance. Earlier USB/control timeouts require separate capture/audio
diagnosis; changing codec bitrate cannot repair a stalled physical device.

On 19 October 2026, a test terminal's C20 returned UVC/ALSA USB timeouts and failed device
opens. Stopping the terminal, cycling C20 power through the existing guarded USB
helper and restarting restored capture. The underlying timeout trigger remains
undetermined; this was an operational recovery, not a new automatic recovery
feature. After the first-picture keyframe retry change and Android 0.3.6's
deferred notification acceptance, four Pi-to-OnePlus calls showed remote video
at both ends (two app-closed, then two app-open, with the phone on cellular data).
The native filter regression passed, including a negative control against the
old first-picture behavior. See `docs/android.md` for the bounded hardware run
and its limitations; it does not establish sustained C20 reliability.

On 25 October 2026, intermittent missing terminal video was reproduced together
with C20 UVC/ALSA control timeouts and failed camera/microphone opens. A guarded
USB power cycle restored the device. The C20 PCM policy above corrects the
incompatible generic capture configuration; it does not establish that every
possible USB timeout has the same trigger. Repeated real phone calls must still
check decoded images at both ends, including alternating callers and USB wake;
configured/sent FPS alone can remain nonzero when the camera has failed.
The C20 was also configured for USB runtime autosuspend after two idle seconds.
The host rule `linux/99-zmalacall-c20.rules` now keeps only that USB device awake
while powered, including after re-enumeration. This removes automatic runtime
suspend from the idle path; it does not change the opt-in guarded five-minute hub
power-off. Confirm `power/control` is `on` on the actual C20 USB device when
investigating an installation or upgrade.

Further checks on the same day reproduced a C20 stall with `power/control=on`
and zero runtime-suspended time. Independent, concurrent ALSA/V4L2 start/stop
cycles also reproduced audio-parameter failures and video `STREAMON` errors,
without either calling application. Runtime-suspend prevention alone is therefore
not a complete resolution of this intermittent device-control failure. A USB
power cycle recovers the tested unit; successful short call sequences cannot
establish that a particular workaround eliminates the fault. Trials of fixed-rate,
interface-close and settling-delay driver quirks were inconclusive; long control
runs also passed without those overrides, so they are not installed as fixes.
Moving the same C20 from a USB 3 port to a USB 2 port did not prevent recurrence.
After an initial playback-volume write, separate 40-cycle audio-duplex and
camera-only checks passed, but concurrent microphone/camera startup failed on
its fifth cycle. An additional control-message-delay trial failed on its
seventeenth combined-media cycle. These comparisons narrow the reproduction
conditions; they do not distinguish camera firmware, cable or host-driver faults.

The C20 camera worker waits for its microphone PCM to remain `RUNNING` for
750 ms before camera open, format negotiation and streaming. Size queries retain
the requested size without opening the camera. The readiness gate uses a
five-second deadline and 20 ms polling, and runs off the UI/media ticker. Stop
cancels and joins the worker; failed camera initialization releases partial
buffers and descriptors. This sequencing addresses a reproduced USB-control
startup interaction without changing the audio rates or relay policy.

The explicit hardware plan `tests/terminal/LLT/c20_media_cycle.py` requires the
terminal service to be stopped. It captures three seconds of native 16 kHz stereo
microphone data and plays native 48 kHz stereo silence, then captures 30 full-HD
MJPEG frames after the microphone has remained `RUNNING` for 750 ms.
Results contain aggregate byte counts; temporary
capture files are removed. Run it with the installed `c20-alsa.conf` policy and a
private `--output` path, specifying the intended `--cycles` count. This verifies
USB media startup, not speech quality, call transport or indefinite reliability.
On October 25 this staged hardware plan completed 50/50 cycles on term2 after
an initial playback-volume write. Native boundary tests also checked the
production worker's readiness reset, timeout, cancellation and cleanup paths.
The installed startup sequence also completed eight terminal/OnePlus calls in
alternating directions, including an app-closed call and two calls after verified
USB power-off/wake. Both ends displayed actual camera pictures in every call.
These bounded checks do not establish indefinite hardware reliability.

The eight October 25 calls with the startup sequence through the encrypted relay
made received video available about 2.1–3.6 seconds after answer at the terminal and 2.2–2.7 seconds at
the OnePlus phone. Phone measurements use its decoded-frame callback; the Pi
measurement uses the decoded-video gate sampled by its UI. These are bounded
samples with healthy C20 media, not a latency guarantee or display-scanout measure.
The earlier failed C20 control-stall case is excluded from that timing range.
In the captured successful trace, relay ICE checks completed about 1.9
seconds after answer, before the first usable video picture.

### Automatic framing

Framing defaults off, is per-terminal and currently supports the Pi C20 only.
Windows leaves its view unchanged. The detector samples the uncropped picture
every two seconds, frames the group with margin, and limits digital zoom to 1–2×.
Zoom-in needs stable observations; new people outside the crop widen promptly.
Pan/zoom ease over about two seconds. Temporary misses retain people for six
seconds; no people or detector failure returns wide, with an eight-second native
watchdog. New calls start wide and discard previous session results.

At 2×, a 1080p source contains only a 960×540 crop enlarged to the output; digital
zoom adds no optical detail. People on a TV or in a photo can be detected too.
No images are normally saved or sent to the server for inference.

The installer prepares LiteRT 2.3.0 and a checksum-pinned SSD MobileNet V2 COCO
quantized model (Apache-2.0, 300×300 input). A lower-priority worker thread uses two
inference threads and one replaceable thumbnail slot; media never waits for it.
Session/sample tokens reject old results after toggles, size changes or calls.
The MJPEG worker crops YUV once for preview and encoder. With framing off/wide,
decoded frames pass through without a crop copy. CPU affinity is not restricted.
Repair an omitted/broken runtime from the installed project using
`sudo sh build_tools/linux/setup-auto-framing.sh`, then restart the terminal.
Source archives omit downloaded models/runtime; calls never download them.

## Appliance services, storage and peripherals

```sh
sudo systemctl status zmalacall-terminal zmalacall-display zmalacall-pairing
sudo systemctl restart zmalacall-terminal
sudo systemctl stop zmalacall-terminal zmalacall-display
sudo systemctl start zmalacall-display
sudo journalctl -u zmalacall-terminal -u zmalacall-display -b
```

Use `disable --now` for both terminal/display services to disable autostart.
Display controls the separate compositor; CEC and pairing have separate services.
Application failures restart automatically, while explicit stops stay stopped.
Code is root-owned under `/opt/zmalacall/releases`; private state is in
`/var/lib/zmalacall`. `current` changes after preparation and `previous` retains
the old release. This is not transactional rollback of OS/configuration/data.

SSH is Ethernet-only after installation. Its nftables guard covers configured
ports, IPv4/IPv6 and traffic arriving over Wi-Fi even if addressed to Ethernet.
Preserve its include/service dependencies. The application runs without root;
scoped Polkit, input permissions and fixed-action helpers handle required hardware.

Journals are volatile/capped at 64 MiB; zram replaces SD-backed swap, `/tmp` is
RAM-backed and root uses `noatime`. Locks/status live under `/run/zmalacall`.
Enrollment, Bluetooth/Wi-Fi, settings, photos and SDK security databases remain
persistent. Export logs before reboot. To enable bounded verbose diagnostics:

```sh
python3 /opt/zmalacall/current/build_tools/linux/diagnostics.py 10
sudo journalctl -u zmalacall-terminal -f
python3 /opt/zmalacall/current/build_tools/linux/check-low-wear.py
```

Diagnostics expires after the selected minutes (maximum 60) or restart; use `0`
to stop early. The filesystem remains writable; this is not a read-only overlay.

### Argon fan

The Windows installer enables fan control; manual installs use `--argon-one`.
It is off outside connected calls, 55% during calls and 100% at 65°C during calls.
Hangup/stop requests fan-off. Reads/writes run off the UI thread. There is no
outside-call thermal override; firmware throttling remains active. Only I2C bus 1,
address `0x1a`, duty values 0–100 are used. Power-button/IR/vendor power-mode
software is not installed. An enabled competing `argononed` causes install refusal.

### Optional USB power control

This experiment is not enabled by the regular installer. The Pi 4's external USB
ports switch together, including the C20 and charger. It cuts power only after
five minutes without terminal activity with a fresh remote battery reading of at
least 25%. Every button press (even consumed or debounced), volume adjustment and
accepted incoming call wakes the worker immediately, before TV routing or answer
timers. Calls/ringing/setup/settings, held buttons, low/unknown battery or a stale
app heartbeat restore or retain power. The idle interval starts when ongoing
activity ends. Another peripheral or open media handles blocks shutdown.
Do not use with USB storage; disable before attaching extra equipment to an
unpowered port, where it cannot yet be detected.

Enable on a matching installed release:

```sh
sudo sh /opt/zmalacall/current/build_tools/linux/install-usb-power.sh zmala
sudo systemctl restart zmalacall-terminal
```

The helper deauthorizes C20 interfaces before switching; wake waits for camera/
audio enumeration, refreshes SDK devices on their owning thread and reapplies
volume. Operations run off-thread and fail toward power-on. A stop hook restores
power after app exit. Status is `/run/zmalacall/usb-power.json`. Wake adds device
startup latency before auto-answer; no electrical energy-saving claim is made.

The webcam icon immediately left of the battery represents shared USB power. Its
gap before the battery matches the gap after Bluetooth. It uses the compact status
style: mint means powered, grey with a slash means off, and a grey question mark
means transitioning or unconfirmed. The helper checks all ports of both shared
hubs after switching; `powered` in the runtime JSON and the icon reflect that
confirmation, independently of camera/SDK readiness. Settings hides this strip,
and installations without the experiment omit the USB icon.

Disable while preserving power:

```sh
sudo systemctl stop zmalacall-terminal
sudo /usr/local/libexec/zmala-usb-power on
sudo rm /etc/systemd/system/zmalacall-terminal.service.d/usb-power.conf
sudo systemctl daemon-reload
sudo systemctl start zmalacall-terminal
```

## Windows/source launch and architecture

`Start ZmalaCall Terminal.cmd` prepares the Windows runtime and starts the regular
profile; `-Fullscreen` is optional. `-Unconfigured` uses a separate fresh QR
profile, and `-ConnectWifi` makes that profile join the scanned network instead
of validating the existing link. `Stop ZmalaCall Terminal.cmd` stops both managed
profiles, checking executable/start time before using recorded PIDs. It does not
stop the server or directly launched Python processes. Direct entry:

```sh
python -m zmala_terminal.common.main --fullscreen --bootstrap /path/to/terminal.json
```

Use a separate `--profile NAME` for another instance and different account
credentials for simultaneous registrations. Connection JSON contains
`server_url`, `device_id`, `device_token`; keep it private and use the reachable
Linux server, not a stale localhost bootstrap. Windows runtime is Liblinphone
5.4.98 with Tk, ANGLE graphics bridges and OpenH264; dependencies remain in
`build_tools/runtime`. Source state remains in `zmala_terminal/data/`.

Text uses GDI+ on Windows and Pango/Cairo/Noto on Linux, including complex-script
shaping. LRU pixel budgets are 8 MiB text, 32 MiB rendered portraits, 24 MiB source
portraits and 2 MiB icons; Linux adds 8 MiB flattened backgrounds. Active widget
references and transient/native allocations are outside these budgets. Before
portrait decoding, PNG/JPEG headers are limited to 2 MiB encoded, 4096 per side
and 4,194,304 pixels total. Invalid images fall back to initials. Photo downloads
use one worker, a 40-path queue, atomic publication and one-minute failure backoff.

## Verification and troubleshooting

Requirement-based unit tests live in `tests/terminal/LLT/`; system and integration
scenarios live in `tests/terminal/HLT/`. Their leading comments identify the test,
linked requirements, procedure and expected observations. Installer unit tests
are included in `make test-adhoc`, outside Pi runtime RBT coverage. They exercise release preparation with temporary
state, including restoration of directory mode 0700 after archive copying so an
imported directory cannot make enrollment credentials readable to other users. See `docs/general.md` for trace validation and
the generated trace report. Every terminal LLR has direct unit-test links and
every HLR has a system-test plan; validation rejects additions without a
corresponding test. This does not establish complete behavioral or hardware coverage.

`xvfb-run -a make test-hlt test-hlt-display` runs controller/HTTP/Tk integration
and the standalone display scenarios. The controller fixtures use real queues,
worker threads, input file handlers and persistence, substituting native devices,
CEC transport and privileged hardware writes. They cover stale replies, rejected
settings, remote releases, relative volume, notification persistence, USB wake,
fan transitions, TV restoration and framing cancellation. Inspect each plan's
limits before treating a result as device acceptance.

After a Pi reboot, run `sudo env ZMALA_INSTALLED_HOST_TESTS=terminal python3 -m
unittest tests.terminal.HLT.test_installed_storage -v` from a prepared checkout
to inspect effective storage policy. This is read-only and skips by default.
For real network/reboot acceptance, `tests/terminal/HLT/network_restart.py`
requires both Ethernet and a configured controlled Wi-Fi access point. Run it
as root with `--before --provisioning <profile>/provisioning.json --evidence
<private-path>/network.json`, reboot normally, then repeat with `--after`.
It binds authenticated requests separately to both interfaces and compares the
Wi-Fi UUID, terminal identity and boot ID. It neither reboots nor changes network
settings, and it does not retain credentials. Record the two results together.

The terminal requirements rewrite has a local [verification report](../tests/coverage/terminal-rebaseline/index.html).
It separates measured LLT coverage, executed HLTs and unverified scenarios. The
report is generated output, not part of the requirement baseline.

Portable tests do not operate the TV or prove native SDK compatibility. For real
rendering use `tests/terminal/HLT/render_cache_ui.py` (Linux under Xvfb);
`--benchmark` measures synthetic cache pressure. UI probes such as `settings_ui.py`,
`tv_setup_ui.py` and `terminal_languages_ui.py` exercise layouts without CEC.
`tests/support/terminal/run-native.sh` checks JPEG workers, preview pixels,
framing, stale tokens, camera-failure size retention, coalesced recovery, encoder
buffer reuse/exact-size scaler bypass and UBSan
paths; a Pi run additionally covers ARM NEON. The opt-in hardware resize scenario
is `tests/terminal/HLT/test-video-resize.c`; its header gives the build command
and idle-device prerequisite. Native size readback and QR-worker lifecycle checks
also live under HLT and require the installed SDK.
Exploratory encoder/decoder probes in `tests/adhoc/native/` and Windows
`tests/adhoc/tooling/h264_decoder_native.py` need their respective native SDKs.

Live HLTs and shared fixtures under `tests/support/terminal/` can use real cameras/accounts: read their
entry points first, use disposable accounts, and stop any normal terminal whose
registration/camera would conflict. Launcher integration tests start/stop actual
terminal processes. Windows-specific launcher checks live under `tests/adhoc/`.
Restore normal services and volume after tests. Run hardware HLTs separately and
record their IDs/platform/results; a portable pass does not qualify them.

| Symptom | First checks |
| --- | --- |
| No TV image | Power/input/cable, `zmalacall-display`, EDID and selected HDMI/CEC adapter |
| Remote unavailable | Charge/power, BlueZ pairing/adapter state, pairing service and input-device readiness |
| Server QR rejected | Current URL/token/ID, reachable server, correct QR and account association |
| Pixelated/slow video | Actual negotiated/captured dimensions, exposure, bitrate, CPU/thermal state, jitter/loss |
| No C20 audio and video | Kernel USB errors and independent capture/audio probes before blaming SIP or codecs |
| Call connected but no sound | C20 connection and effective call routes, actual decoded levels and physical listening in both directions |
| Old backup rejected | Follow server re-enrollment recovery; do not disable revision checks |

Long idle/repeated calls, USB reconnect/power faults, network loss, CEC across TV
models, echo/listening and intended-user readability still need physical acceptance.
Keep failures distinct from old tests on different hardware. Remaining engineering
work is in [astra.md](../astra.md).


## Secure relay transport

A server can select `secure_calls.mode = tls-relay` in its authenticated HTTPS
configuration. The terminal disables SIP UDP/plain TCP, enables SIP TLS, verifies
the server certificate and name against the local CA bundle, and requires SRTP
for outgoing and incoming media. ICE gathers TURN candidates through TLS on the
configured port (443 by default) and forces relay selection. Separate SIP/TURN
ports support a single public server IP. Network failure does not trigger plaintext fallback.
The installed trust store is authoritative; a server response cannot supply a CA.
For a private deployment, install its CA in the OS trust store before enrollment.
`SSL_CERT_FILE` can select a locally administered CA bundle for both HTTPS and SIP.

Configuration validation rejects incomplete or expired TURN credentials and secure
configuration received through an HTTP enrollment. Re-enroll using the server's
new HTTPS QR code when changing deployment mode. Hourly credential changes rebuild
the core only while idle, preserving active calls. An offline cache with expired
credentials cannot start a secure call; reconnect to the configuration server.
The normal user call and answer controls do not change.

Debian Trixie mediastreamer2 5.3.105 has a fragmented TURN ChannelData padding bug
which breaks SRTP authentication. `build_tools/linux/build-turn.py` fetches pinned,
SHA-256-checked upstream source, applies the framing, complete-write and socket-error
patches under `linux/native/`, and builds
a process-local interposition library under `linux/turn-runtime/`. The original
parser must reproduce the defect; the corrected parser must pass 3,804 chunk sizes.
The socket callback fixture must likewise fail on original EAGAIN handling and
pass with the correction, including a successful retry and real peer closure.
The installer runs this build on the target architecture and retains upstream source
and test evidence. It does not replace the system SDK library. Upstream source is
AGPL-3.0-or-later, with its original notices retained in the downloaded files.

The Linux launcher checks the exact installed Debian SDK package version before
loading this library with `LD_PRELOAD`. A version mismatch stops startup and requires
rebuilding/requalifying the correction. Secure mode refuses to run without the loaded
correction. Ordinary LAN-only source launches can run without it. No ARM binary or
local SDK source download is committed. See the server guide for endpoint routing,
certificates, coturn configuration and network limitations.

## Android companion accounts

ZmalaPhone uses the same palette and logo with an **App** account. Pi enrollment still requires a **Terminal** account. An account cannot belong to both; changing its type revokes its previous device and SIP credentials and requires a fresh setup QR. ZmalaPhone supports LAN or encrypted relay calls and Firebase incoming alerts while closed. A blue App contact can be reached through push without an active SIP registration; delivery still depends on notification permission and connectivity. Both clients must use HTTPS enrollment when secure mode is enabled. See [Android implementation](android.md) for build and qualification status.


### Contact presence colours

Contacts distinguish confirmed activity from unconfirmed push delivery: **Available**
(green) means a current SIP registration remains reachable under the server's
five-second checks; **Try calling** (blue) means only push eligibility remains;
**Offline** (red) means neither. Both green and blue permit an attempted call.
A push registration is not proof that the app is installed, online or ready to answer.
The API adds `presence` (`available`, `push`, `offline`) to full, delta and preflight
responses; `online` remains true for both callable states for older clients.
Terminal live information expires after six seconds without a successful refresh,
and cached configurations discard both live fields. Android clears the directory
when a configuration refresh fails. Name buttons show a smaller status line;
terminal cards show the status with a check, question mark or cross. New terminal
labels are translated in English and French, with English fallback elsewhere.

Terminal cards reserve a 56-pixel status area below the name, with separate
regions for the symbol and shaped label. Text fits within 48 pixels vertically
at no less than 11 points; exceptionally narrow cards elide overflow while keeping
combining marks with their base. French status phrases fit in full in the 720p
and full-HD three/five-card TV layouts. Animation uses the smallest card's label
width to reuse shaped images without overlapping the symbol. The display HLT
checks actual text/icon bounds, rather than only the coloured band's rectangle.

Incoming callback requests from a current app contact show a persistent yellow flag banner over that contact portrait, including adjacent cards. The localized callback-requested label stays separate from the name and availability. The flag disappears when the server reports cancellation or completion. Outgoing requests keep their existing return-arrow tag and cancellation controls. Neither marker starts a call.

When an outgoing call ends before answer, including timeout, refusal or caller cancellation, the terminal offers to request a callback from the same contact. Green submits the request; red returns home. It waits for media teardown, does not repeat an existing pending request, and does not show this question after a connected call or declined incoming call. Late native events cannot dismiss the offer or start a cancelled call.
