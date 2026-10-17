# ZmalaCall

## Download the terminal installer

Download **`zmala_terminal_setup.exe`** and the installation guide from the
[latest public release](https://github.com/toastfr35/ZmalaCall/releases/latest).
No GitHub account is required. Release assets include SHA-256 checksums.
The installer targets a Raspberry Pi 4 with Raspberry Pi OS Lite (64-bit),
Debian 13 Trixie; see the included guide for flashing and connections.

## Raspberry Pi server

`zmala_server_setup.exe` installs the server on a Pi 3 or 4 running Raspberry Pi
OS Lite 64-bit Trixie. It supports GUI confirmation, headless deployment, optional
data migration, automatic startup, Ethernet-only SSH and RAM-based logs/swap.
See the [server installation guide](docs/pi-server-installation.md) for setup,
build commands and the admin control for switching wired SSH on or off.

## Repository

Source is maintained in the public [toastfr35/ZmalaCall repository](https://github.com/toastfr35/ZmalaCall).

```powershell
git clone https://github.com/toastfr35/ZmalaCall.git
Set-Location ZmalaCall
npm.cmd ci
npm.cmd --prefix zmala_server ci --ignore-scripts
```

The existing development folder can be used directly as a Git checkout. Local
`data/` folders, credentials, personal portrait drafts, downloaded runtimes,
temporary files, and distribution archives are ignored. Keep independent
backups of local configuration and account photos; they are not in the repository.
The launchers and setup tools prepare runtime dependencies as described below.

## Development checks

The top-level [Makefile](Makefile) runs correctness checks without starting the
server, terminal, installers or live hardware tests. Install development tools:

```sh
npm ci
npm --prefix zmala_server ci --ignore-scripts
python -m venv .venv
# Linux/macOS:
.venv/bin/python -m pip install -r requirements-dev.txt
# Windows PowerShell:
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

Install GNU Make, a POSIX `sh`, and Cppcheck 2.21 or newer. On Debian these are
available as `make`, `dash`, and `cppcheck` packages (older Cppcheck versions may
need upgrading). On Windows with MSYS2, install `make` and
`mingw-w64-ucrt-x86_64-cppcheck`; this checkout detects the usual Cppcheck and
shell paths under `C:/msys64`. Run:

```sh
make lint
make test
```

On this Windows PC, GNU Make can be invoked from PowerShell with
`& C:/msys64/usr/bin/make.exe lint`. Override tool locations with `PYTHON=...`,
`NODE=...`, `CPPCHECK=...`, or `POWERSHELL=...`; set the environment
variable `LINT_SH` to select a shell outside PATH.

`make lint` includes ESLint for server/admin/tool JavaScript, TypeScript checking
of the migrated server modules, Ruff for Python,
Cppcheck for C/C++/Arduino sources, shell syntax checks, Prettier checks and
generated admin asset verification. On Windows it also parses PowerShell scripts
without executing them. Elsewhere, run `make lint-powershell POWERSHELL=pwsh` if
PowerShell is installed. Each check has a matching `lint-*` target. Missing tools
and reported errors fail the target; generated assets and downloaded runtimes
are excluded from source linting. Native checks are static analysis, not a
replacement for SDK/Arduino builds or Pi call tests. Shell and PowerShell checks
validate syntax rather than running a full semantic script analyzer.

Edit `zmala_server/web/admin-*.js` and `web/styles/*.css`, then run
`npm run build:admin`; `admin.js` and `admin.css` are generated outputs. Keep
comments focused on ownership, protocol constraints, threading, cancellation
and other behavior that is not apparent from the code. Routine forwarding
functions and named test assertions need no line-by-line narration.

The server runtime and admin source modules use strict TypeScript checking of
JavaScript and typed JSDoc without a runtime compilation step. Shared contracts
live in `zmala_server/types/`; separate configurations check Node services and
browser controllers. Run `npm run typecheck` or `make lint-types` independently.
The generated admin bundle, vendored dependencies and JavaScript tests are not
part of this type-checking scope. See the
[implementation guide](docs/implementation.md) for persistence boundaries and
the maintained local SIP transport patch.

The server runs on this Windows PC. The terminal runs on Windows or Linux (including Raspberry Pi). Linphone runs on your phone. Connect the phone to the same Wi-Fi/LAN as the PC.

| Component | Where to access it | Purpose |
|---|---|---|
| Server | Administration page at `http://127.0.0.1:8080/` on the PC | Accounts, contacts, settings, SIP signalling and audio/video relay |
| Terminal | Separate **ZmalaCall** desktop window on Windows or Linux | Dark carousel interface controlled by keyboard or physical buttons |
| Linphone client | Linphone app on the phone | Family member's SIP video client |

The current PC address is **192.168.1.118**. On the phone, `127.0.0.1` refers to the phone itself: use the PC's LAN address in Linphone.

Run the PowerShell examples below from the project directory:

```powershell
Set-Location 'W:\tmp\videocall'
```

Linux installation, setup, scripts and Pi 3 test results: [Linux terminal guide](docs/linux-terminal.md). The Windows instructions below remain available for PC testing.

The Linux package targets the Nuroum C20: MJPEG capture, Pi hardware H.264
encoding, software decoding and C20 microphone/speaker/ringer. It discovers
those devices automatically and defaults to the verified 720p/15 fps preset.
Windows retains server-selected devices and VP8/H.264 for PC testing. See
[C20 media and verification](docs/pi-hardware-video.md).

The Raspberry Pi installer is [ZmalaCall-Terminal-rpi.tar.gz](build_tools/dist/ZmalaCall-Terminal-rpi.tar.gz). Extract it on Raspberry Pi OS / Debian 13 ARM64 and run `sudo ./install.sh`. It installs the display session and terminal, starts QR setup, and enables automatic startup at boot. See the Linux guide for enrollment, upgrades and service commands.

## Project layout

```text
zmala_terminal/   Shared terminal code, OS adapters, assets, translations and local data
  tests/          Terminal unit, setup, UI and media tests
zmala_server/     Node server, admin pages, assets and server data
  tests/          API, SIP, media-relay, console and PDF tests
docs/             Design, Doorstop requirements and generated catalogues
build_tools/      Windows launchers, SDK setup and graphics build tools
  linux/          Linux installation, packaging and terminal launchers
  tests/          Windows launcher integration checks
  runtime/        Downloaded native SDKs and PDF QA dependencies
  data/           Managed process records
```

The five root launchers control the terminal and server independently:

| Script | Action |
|---|---|
| **Start ZmalaCall Terminal.cmd** | Open the regular terminal |
| **Stop ZmalaCall Terminal.cmd** | Stop the regular and unconfigured managed terminals |
| **Start ZmalaCall Terminal Unconfigured.cmd** | Open a fresh, separate QR-setup profile |
| **Start ZmalaCall Server.cmd** | Start the server and open administration |
| **Stop ZmalaCall Server.cmd** | Stop only the server |

Starting a terminal does not start the server. Starting the server does not start a terminal or require Python/native terminal libraries. Start scripts reuse their existing managed instance; stop scripts are safe to run again. They track executable paths and process start times to avoid stopping unrelated processes. The old combined launchers have been removed.

Server administration opens through `zmala_server/data/open-admin.url`. The current design and requirements are in [docs/](docs/README.md). Run `build_tools/doorstop.cmd` to manage requirements and `build_tools/publish-requirements.ps1` to regenerate the Markdown catalogues.

## 1. Server

### How to install

1. Open a PowerShell session in the cloned project directory (`W:\tmp\videocall` on this development PC).
2. Install Node.js with npm if needed. This PC already has Node.js **24.20.0**.
3. Install the server dependencies:

   ```powershell
   npm.cmd --prefix zmala_server ci --cache .\build_tools\.npm-cache --ignore-scripts
   ```

The server launcher installs missing npm dependencies on first start. It does not check Python or prepare the terminal runtime.

Accounts and settings persist in `zmala_server/data/server.json`. The server creates `zmala_terminal/data/terminal.json` for the terminal and `zmala_server/data/open-admin.url` for administration. Keep both components’ `data/` directories private: they contain credentials and contact photos.

### How to start

Start the server without launching the terminal:

```powershell
& '.\Start ZmalaCall Server.cmd'
```

This also opens administration. To keep the browser closed:

```powershell
& '.\Start ZmalaCall Server.cmd' -NoBrowser
```

The launcher reuses the managed server if it is already running and leaves terminal processes alone.

To stop only the server, double-click **Stop ZmalaCall Server.cmd**, or run:

```powershell
& '.\Stop ZmalaCall Server.cmd'
```

### How to use

Open **`zmala_server/data/open-admin.url`** on the server PC, or browse to **`http://192.168.1.118:8080/`** from another computer on this LAN. On a fresh installation, the first visitor sets the shared admin password; this also works remotely. Subsequent visits require that password, with no username. Use **Change password** or **Sign out** in the sidebar. See [administration authentication](docs/admin-authentication.md) for sessions, recovery and optional HTTPS.

The current phone SIP login is **`phone1` / `test`**. Administration uses the private shortcut above, rather than that SIP login.

Administration opens in dark mode. The sidebar opens separate pages with their own URLs; account edits, connection details and deletion use modal dialogs. Terminal settings are inline in the selected terminal’s card.

1. **Overview** (`/`) shows account counts, live state, the shared SIP server and terminal status.
2. **Accounts** (`/accounts`): click **New account** to enter a username, display name, one or more email addresses, type (**Linphone** or **Terminal**) and password. Separate email addresses with commas; up to ten are supported. Leave the password blank to generate one. Use a row's pencil button to edit it, including its username; leave the password blank to keep it. Use its trash button to open deletion confirmation. Search and type filters help find accounts. Close an account's active call before changing its username, type or password, or deleting it.
3. Account pictures are optional. Upload or remove a picture in the **account edit dialog**; it appears in the terminal selector. Accounts without pictures show an initial. All six testing accounts have fictional portraits generated with the built-in image tool; see [sample assets and prompts](zmala_server/assets/test-portraits/README.md). Contacts always use their account picture. Under **Terminals → Calls**, each terminal has **Auto-answer incoming calls** and a 5–600 second answer delay. This setting applies to every permitted incoming caller. Linphone accounts do not have auto-answer settings.
4. **Groups** (`/groups`): use **New group** to set a name, description and members. Edit or delete groups using their card buttons and modal dialogs. Any two accounts sharing a group can call each other in both directions. An account can belong to several groups; membership does not grant access to other groups’ members. New accounts need to join a shared group before they can call another account. Self-calls are disabled.
5. On **Accounts**, use a row's chain-link button to open **Connection details**. Credentials are individually copyable and passwords can be revealed. Every account uses the same domain and SIP server. Terminal details also offer **Use on this PC** and **Download setup**.
6. **Terminals** (`/terminals`): select a terminal by its persistent serial number. **Account association** selects the terminal account used by that serial. Changing to an account associated with another terminal swaps the two associations; serials, enrollment credentials, device settings and console history stay with the physical terminals. Both accounts must be idle. **Terminal settings** contains language, camera, microphone, speaker, audio processing, video resolution and auto-answer with a 5–600 second delay. Account names, usernames, email addresses, passwords and pictures are managed only on **Accounts**; call permissions are managed on **Groups**. Settings are grouped into Calls, Video & audio and General, with one Save changes action. The footer has QR PDF downloads under Setup and a Console action; command shell preferences are edited in Console. Changes apply automatically; media changes wait until idle. Administration stays in English.
7. **Activity** (`/activity`) shows registered accounts, active call counts and recent events. Live state updates automatically.
8. **Callbacks** (`/callbacks`) lists requests and their Linphone/email delivery status. Use **Edit deadlines** to set **Email reminder after (hours)** and **Remove request after (hours)**. Both run from request creation; fractional hours are supported, removal must be later, and changes apply to pending requests. Administrators can cancel pending requests. **Email server** configures SMTP; **Check connection** checks authentication without sending mail.

Permission changes affect new calls. A blocked caller cannot ring or be auto-answered. Deleting an account removes its group memberships, registration and device access. Renaming preserves its password, group memberships, account picture, terminal identity and assignment, while changing its SIP address. Update the username in Linphone after renaming; connected terminals receive it automatically.

Upgrades preserve existing accounts and credentials. Old mutual call permissions migrate to two-member groups, preserving access without granting calls between unrelated accounts. Old one-way permissions need a shared group to enable two-way calling. Existing per-contact auto-answer flags migrate to one Terminal account setting: it is enabled if any previously permitted caller had auto-answer enabled. Once enabled, it applies to all permitted incoming callers.

Device changes take effect while the terminal is idle. PNG/JPEG uploads up to 2 MB are resized into PNGs. Configuration is versioned and cached by the terminal.

| Service | Address / ports |
|---|---|
| Administration and terminal configuration | `127.0.0.1:8080`, accessible on this PC |
| SIP signalling | UDP/TCP `5060` on the PC's network interfaces |
| Audio/video relay | UDP `20000–20199` |

Windows Firewall must allow Node.js on the private network. If startup fails, check `zmala_server/data/server-error.log` and whether another application is using ports 5060 or 8080. Routine events are in `zmala_server/data/server.log`. The address `http://127.0.0.1:8080/health` returns `{"ok":true}` when the HTTP server is running.

If the PC's LAN address changes, stop the applications and set the new address before starting, for example:

```powershell
& '.\Stop ZmalaCall Terminal.cmd'
& '.\Stop ZmalaCall Server.cmd'
$env:VIDEOCALL_HOST = '192.168.1.120'
& '.\Start ZmalaCall Server.cmd'
& '.\Start ZmalaCall Terminal.cmd'
```

Update Linphone's domain, proxy and terminal SIP address to match. Accounts and passwords are preserved.

### Callback email reminders

1. Enter each account's real **Email addresses** on Accounts or in its terminal card. New accounts require one or more; existing accounts without addresses show **Email address needed**. Separate addresses with commas.
2. On **Callbacks → Email server**, enter your provider's SMTP host, port, username, password or app password, and sender email. Choose **STARTTLS** (usually port 587) or **TLS** (usually port 465). Unencrypted mode is provided for local mail relays. Enable reminders and save. A blank password preserves the saved one; **Clear saved password** removes it.
3. Click **Check connection** to check connectivity and authentication without sending an email. Your provider must also allow sending from the chosen sender address.
4. Use **Edit deadlines** to set **Email reminder after (hours)** and **Remove request after (hours)**. Defaults are **1 hour** and **4 hours**. For 30 minutes, enter **0.5**. Both delays run from creation time, and changes apply to existing pending requests.

At the reminder deadline, a pending request sends a separate email to each of the contact's addresses, including while their phone is offline. Email and Linphone notification are independent. Successful SMTP recipients are recorded; failed recipients retry once a minute until the request completes, is cancelled or reaches removal. SMTP acceptance does not prove inbox delivery or reading. At the removal deadline, a pending request disappears from the page, terminal configuration and saved request data. Completed and cancelled requests remain in bounded history.

SMTP settings and passwords stay in the private server configuration. Passwords are omitted from admin responses, and contact email addresses are not included in terminal configuration. Reminders start disabled until SMTP is configured.

## 2. Terminal

### How to install

The terminal code is included under `zmala_terminal/`. Its requirements are:

| Requirement | Installed on this PC |
|---|---|
| 64-bit Windows Python with Tkinter and ctypes; Python 3.11 or newer for runtime setup | `C:\msys64\ucrt64\bin\python.exe` |
| Windows x64 GCC on PATH, for initial graphics bridge compilation | `C:\tools\perl\c\bin\gcc.exe` |
| Liblinphone, desktop ANGLE and OpenH264 | Prepared under `build_tools/runtime/` |

Double-click **Start ZmalaCall Terminal.cmd**. On first launch, it downloads missing pinned runtime packages, verifies their SHA-256 checksums and builds the graphics bridges. Initial setup needs Internet access. This PC's runtime is already prepared. No Node.js or npm is required to launch the terminal.

To prepare the runtime explicitly, with the applications stopped:

```powershell
& 'C:\msys64\ucrt64\bin\python.exe' '.\build_tools\setup-runtime.py'
```

To use another Windows Python, set its executable path before launching:

```powershell
$env:VIDEOCALL_PYTHON = 'C:\path\to\python.exe'
& '.\Start ZmalaCall Terminal.cmd'
```

The launcher checks Python using `build_tools/check-python.py`. No Python package installation is needed for the terminal itself.

### How to start

Double-click **`W:\tmp\videocall\Start ZmalaCall Terminal.cmd`** in File Explorer. It opens the **ZmalaCall** desktop window in your session. Start the server separately with **Start ZmalaCall Server.cmd** when you want calls and configuration updates. The terminal can open while the server is stopped, using its saved configuration and showing offline status.

The default Windows terminal uses the account selected through **Accounts → Connection details → Use on this PC**. Choose a Terminal account there, close the existing terminal window, then start it again to apply the selection. Its username becomes its SIP address: for example, a Terminal account named `lounge` receives calls at `sip:lounge@192.168.1.118`.

To start a new terminal in full screen:

```powershell
& '.\Start ZmalaCall Terminal.cmd' -Fullscreen
```

Select **ZmalaCall** from the taskbar or **Alt+Tab**. Wait for the server indicator to turn green. The terminal's video interface is in this desktop window; port 8080 serves administration.

Close the ZmalaCall window to stop that terminal, or use **Stop ZmalaCall Terminal.cmd** to stop both managed terminal profiles. The server continues running. Stop scripts do not erase configuration; **Stop ZmalaCall Server.cmd** only stops the server.

### How to use

| Key / button | Idle | Incoming call | Outgoing call | In call |
|---|---|---|---|---|
| LEFT / RIGHT | Select contact | No action | No action | No action |
| ENTER / GREEN | Show call confirmation | Answer | No action | No action |
| ESC / RED | Hold 10s to open settings | Decline | Cancel | Hang up |

- **Call the phone:** select an online contact with LEFT/RIGHT, then press ENTER/GREEN. Their account picture appears with **“Do you want to call Noah?”** (using that person's display name), a large green check with **Yes** and a red cross with **No**, matching the physical buttons. Press ENTER/GREEN a second time to call. Any other key or button returns to the carousel without changing the selection. Holding GREEN does not confirm. Availability and group permission are checked again before dialing.
- **Request a callback:** select an offline contact and press ENTER/GREEN. Their picture and name appear with a red **“Currently unavailable”** message, **“Do you want to request a callback?”**, and the same green **Yes** / red **No** prompts. Press ENTER/GREEN again to send the request; any other key cancels. The prompts disappear while submission is in progress. The terminal shows **“Callback requested”** after the server confirms it was saved. A failed submission shows the existing unavailable message.
- **Missed calls and texts:** if a caller hangs up while the terminal is still ringing, ringing stops and that person's notification count increases. Their carousel picture shows a red badge with a white handset and a numbered dark bubble. Each new text message from a phone sharing a group increases the same counter; its body is not shown and an ongoing call continues. The top-left badge shows the combined unread total, even when flagged contacts are visible. The ZmalaCall logo returns after all notifications are acknowledged. Browsing keeps the counters. Press ENTER/GREEN to open a contact's call or callback confirmation and clear all their notifications, even if you then cancel. Counts survive a terminal restart; old saved flags become a count of one. Counts above 99 show **99+**. Answered and deliberately declined calls do not increase counts. Texts require the terminal to be online and are not queued for later delivery.
- **Answer the phone:** when the terminal rings, press ENTER.
- **End the call:** press ESC.
- **Toggle full screen:** press F11.

Under **Terminals → General → Carousel portraits**, choose **3 portraits** (default) or **5 portraits** for each terminal. The five-portrait layout also fits a 720p display; fewer than five contacts use three positions. Changes apply when the terminal returns to its idle screen. The terminal uses a dark carousel: the central person is selected, with neighboring people on either side and navigation arrows at the edges. LEFT/RIGHT wraps through the contacts with a short sliding and scaling animation. ENTER can open the call confirmation immediately during the transition. With fewer than three contacts, unused slots are empty. There are no on-screen buttons, footer instructions or terminal name at the top. Incoming calls show expanding green halos, a pulsing portrait border and a phone symbol; these stop when answered or declined. Change display names and pictures on the Accounts page; contacts are always sorted alphabetically.

During a connected call, absent incoming video shows a large camera symbol and **“No video from the other person” / “You can still talk”**, translated into the terminal's language. Audio and the terminal's outgoing video continue. The message automatically disappears when a video frame is decoded. If frames stop arriving for four seconds, or the other person disables video through SIP negotiation, it returns. It makes no assumption about whether the cause is their camera setting or a connection problem.

Each contact shows a large **green check + Online** or **red cross + Offline** band, translated into the terminal's language. Offline contacts remain visible; ENTER/GREEN offers a callback request without attempting a SIP call. The server probes registered devices every five seconds with a five-second timeout, so an unresponsive phone appears offline within **15 seconds**, including the terminal's two-second presence refresh. Checks continue while the registration remains valid to detect recovery. Loss of server updates marks contacts offline after six seconds. A fresh server check before dialing also prevents calls to contacts whose status changed since the last update. If someone goes offline while their call confirmation is open, GREEN switches to the callback question for another confirmation.

Callback requests use a configurable removal deadline (default **4 hours**), survive server restarts and are listed under **Administration → Callbacks**, where an administrator can cancel them. Repeated requests to the same person reuse the pending request. When a phone registers again, the server sends a basic SIP chat message to Linphone with the requester's SIP address; Linphone must allow chat and phone notifications to show it. The admin page distinguishes a pending notification from a message accepted by Linphone, which does not prove the person read it. Failed delivery retries while the phone is registered. This does not provide a push notification while Linphone is disconnected.

When both people become available, the terminal waits until the carousel has been idle for five seconds, selects the person and briefly shows **↩ name · Online** at the top. This also handles requests received by another terminal. Press GREEN to open the normal call question and GREEN again to dial; there are no automatic calls. Connecting a call between the two people completes their pending requests. Removing their shared-group permission or deleting an account cancels the request.

Each terminal defaults to English. Choose its language under **Administration → Terminals → General → Language**. The included catalogue has 95 European and Asian language options, covering European national languages and many regional languages, Chinese (Simplified and Traditional), Japanese, Korean, South Asian and Southeast Asian languages, Arabic, Hebrew, Persian and others. Terminal prompts, call questions, callback acknowledgments, call states, countdowns, errors, window title and contact availability labels are translated; account/contact names retain the names you enter. The network indicator uses icons and arrows without text. Windows fonts and native GDI+ text rendering handle Unicode text, complex scripts and right-to-left text. Translations live in `zmala_terminal/shared/terminal-languages.json`, `setup-translations.json`, `wifi-confirmation.json`, `video-messages.json`, `call-questions.json` and `confirmation-prompts.json`; add complete entries to all six to extend the catalogue, then restart the server and terminal.

Choose **Video resolution** in the same **Devices & display** section: **480p (640×480)**, **720p (1280×720)** or **1080p (1920×1080)**, then save. Each terminal has its own setting, applied automatically when idle on Windows and Linux. The presets target 15 fps and adjust video bandwidth together; actual frame rate depends on the camera, terminal and network. New terminals default to 720p. Use 720p for the Pi3/C20: 1080p calls failed the 10 fps minimum in testing. Legacy local video overrides have been removed. Saved 360p settings migrate to 480p because both deployed SDKs reject 640×360. The terminal checks the SDK's applied size and enables negotiated RTCP NACK video retransmission to help recover lost packets on low-latency links. This cannot repair a stalled USB camera or guarantee quality on a congested network.

The compact top-right graphic shows **terminal → Wi-Fi → server**. Green indicates a working connection, red a disconnected link, and gray an unknown state. The network icon checks the PC’s physical network connection (including wired LAN); the server icon also requires SIP registration and recent configuration access. Connectivity icons and missed-call badges use smooth anti-aliased graphics rendered at four times their display resolution and reduced to their final size.

If auto-answer is enabled on the Terminal account, the terminal shows a countdown of at least five seconds for every permitted incoming caller. ESC/RED declines during the countdown. Auto-answer requires incoming-call permission and verified caller information from this server.

The terminal starts from its last valid configuration cache and polls for updates. An unavailable SIP registration disables outgoing calls. Choose the camera, microphone and speaker in administration.

If no window appears or startup fails, check `zmala_terminal/data/terminal.log`, `zmala_terminal/data/terminal-error.log` and `zmala_terminal/data/terminal-native.log`. To display startup errors in a console, stop the managed applications, start only the server and run the terminal in the foreground:

```powershell
& '.\Stop ZmalaCall Terminal.cmd'
& '.\Start ZmalaCall Server.cmd' -NoBrowser
& 'C:\msys64\ucrt64\bin\python.exe' '.\zmala_terminal\main.py'
```

Close this foreground terminal's window to stop it. The launcher does not track terminals started directly with Python.

To run an additional terminal account on this PC, open its **Connection details** on the **Accounts** page and click **Download setup**. Place the downloaded JSON under `zmala_terminal/data/`, then launch a separate instance with its own profile, for example:

```powershell
& 'C:\msys64\ucrt64\bin\python.exe' '.\zmala_terminal\main.py' --bootstrap '.\zmala_terminal\data\terminal-lounge.json' --profile 'terminal-lounge'
```

Use a different profile for each concurrent terminal so its native databases and configuration cache are separate. Close these additional windows yourself; the launchers manage only the regular and unconfigured instances. Terminal configuration access currently remains local to this PC, so this setup file is for Windows instances on the same machine.

### Local settings

From the carousel, hold RED for **ten seconds** to open Settings. A progress bar appears after the first **two seconds** and fills until Settings opens. Releasing early, another button, lost focus, remote disconnection or an incoming call cancels the hold. Short RED presses keep their normal behavior; GREEN confirms calls immediately on its second press.

On the settings list, LEFT/RIGHT selects a setting, GREEN opens it and RED returns to the carousel. Inside an editor, LEFT/RIGHT changes the choice or volume, GREEN saves it to the server and RED discards the draft. Only the active panel shows button hints. Connectivity icons are hidden and the terminal serial appears in small print at the bottom.

The six editable settings are language, automatic answer (**Never, 10 s, 30 s, 1 min, 2 min, 5 min, 10 min**), automatic framing, speaker volume (0–100%), three/five portraits and **Return to TV** (**30 s, 1 min, 2 min, 5 min, 10 min, 20 min, Never**; default **30 s**). A seventh **Reset** entry opens the existing reset confirmation page. Incoming calls interrupt the page and discard unconfirmed edits. Saves require server acknowledgement; failed saves keep the editor open with a localized error. Concurrent server edits are detected instead of silently overwritten. The terminal authenticates with its own device credential and cannot edit another terminal or credentials. Call ringing limits follow the target's answer delay; external SIP apps may impose their own timeout.

When a remote button brings up the UI from another TV input or standby, the terminal remembers that TV state. After ten seconds without a button press, a thin blue bar at the very bottom shows the remaining browsing time. Every remote button restarts the timer and hides the bar for ten seconds; calls, held buttons and settings writes pause it and receive a fresh interval afterward. Expiry discards unconfirmed local edits and restores the saved input or standby. Selecting another TV input yourself releases the timer. There is no countdown without a saved state (for example after restarting the terminal already on its HDMI input), on Windows without CEC, or with **Never** selected. The same timeout is available under **Terminals → General** on the server.

### Factory reset and QR setup

Open Settings by holding RED/ESC for ten seconds, navigate to **Reset**, then press GREEN/ENTER. On the separate confirmation page, GREEN/ENTER resets; RED/ESC keeps the configuration and returns to Settings. Reset clears this terminal's local Wi-Fi/server enrollment and call cache. It preserves server accounts and the other terminal profiles.

The terminal guides setup in this order; the two QR prompts stay the same in every language:

1. **`wifi QR code ?`** — show the Wi-Fi QR until the connection succeeds.
2. **Wi-Fi confirmation** — a large green check, “Wi-Fi connected” and “Next, show the server QR code” appear with a 10-second countdown. These messages use the terminal's language. The camera is paused and QR codes are ignored during this screen.
3. **`server QR code?`** — the scanner resumes automatically; show the server QR for the desired Terminal account. The normal call screen appears after authentication and configuration validation succeed.

In administration, open **Terminals** and find the terminal’s card. It contains **Download Wi-Fi QR PDF**, **Download server QR PDF** and **Console**. The Wi-Fi button opens a dialog for SSID/password; the server button generates setup for the selected terminal. Server PDFs are also available through an account's connection details. Print at 100% and keep the complete QR and its white border visible. The codes contain credentials. Wi-Fi credentials are not stored on the server.

To test from a fresh profile, double-click **Start ZmalaCall Terminal Unconfigured.cmd**. It starts a separate window/profile without starting the server and initially uses this PC's existing network connection; scanning a Wi-Fi QR does not reconnect or disconnect the PC in this test mode. Every new launch of this test profile starts unconfigured; reopening an already-running window keeps its current state. Start the server separately to download QR PDFs and complete server enrollment. The regular terminal's saved configuration is preserved.

Camera scanning runs in an isolated background process. The preview adapter handles camera format changes while preserving the QR decoder. A camera worker failure keeps the setup screen open, shows a red preview border and retries after five seconds. Closing or stopping the terminal also stops its camera worker. Camera diagnostics are in `zmala_terminal/data/qr-camera-error.log`; QR contents are sent through a private pipe and are not written by the application to logs. The launcher prepares `build_tools/runtime/zmala-qr-preview.dll` automatically; runtime setup builds it along with the graphics bridges.

The QR camera preview is not mirrored. Its border updates only when its status changes, avoiding repeated background repaints over the native video.

To actually join the scanned network on a dedicated Windows terminal:

```powershell
& '.\Start ZmalaCall Terminal Unconfigured.cmd' -ConnectWifi
```

This mode uses Windows WLAN, supports WPA2 Personal/AES and open networks, and creates an application-owned per-user profile. Reset removes only that profile. It has not been tested against a live Wi-Fi adapter on this shared PC.

For concurrent tests, use different Terminal accounts. **term2** has been added to the **Family** group, with a test picture and password `test`. Its address is **`sip:term2@192.168.1.118`**. Select `term2` in administration and print its server QR for the unconfigured test window. Keep `term1` assigned to the regular terminal.

### Terminal maintenance console

Open **Terminals**, find the terminal’s card, then choose **Console**. Enter a command for its configured shell, adjust the timeout if needed, and choose **Run command**. The terminal polls every three seconds, executes one command at a time in a background worker using its configured shell, and returns stdout, stderr, status and exit code. Queued commands wait while it is offline. The terminal must be running with the updated code and successfully enrolled.

Each command runs in a fresh, noninteractive process using the terminal’s configured **Command shell**, as its Windows user, with `zmala_terminal/` as its starting directory. The shell is saved with the queued command, so changing the setting affects new commands. Example for Windows PowerShell or PowerShell 7:

```powershell
Get-ComputerInfo | Select-Object WindowsProductName, OsUptime
```

The default timeout is 60 seconds (5–120 allowed); commands and their child processes stop at timeout, reset or terminal close. Combined output is limited to 64 KiB. Shell variables/current directory do not persist between commands; interactive programs and automatic elevation are not supported. Administrator authentication is required for the console. History is saved in `zmala_server/data/console-jobs.json`. Commands are not automatically rerun after a terminal loses contact; a **lost** job has an unknown outcome.

### Launcher names

The five independent product launchers are listed at the top of this README. They call the PowerShell scripts under `build_tools/`. Terminal starts support `-Fullscreen`, the unconfigured start also supports `-ConnectWifi`, and the server start supports `-NoBrowser`.

## 3. Linphone client

### How to install

1. Install **Linphone** on your Android phone or iPhone from its app store.
2. Connect to the same Wi-Fi/LAN as this PC.
3. Add a third-party SIP account with these settings:

   | Setting | Value |
   |---|---|
   | Username | `phone1` |
   | Authentication ID, if requested | `phone1` |
   | Password | `test` |
   | Domain | `192.168.1.118:5060` |
   | Proxy / SIP server, if requested | `sip:192.168.1.118:5060;transport=udp` |
   | Transport | UDP |
   | Media encryption | None |
   | ICE / STUN | Disabled |
   | Video | Enabled |

   If a field expects a complete SIP identity, enter **`sip:phone1@192.168.1.118`**.

4. Save the account and allow camera/microphone access when Linphone requests it.

The fictional sample phone identities are listed below. Set the matching display names and portraits through administration when using these examples. Current membership in **Family**, **Friends** or other groups determines which terminals each phone can call; check **Groups** in administration:

| Username | Example display name |
|---|---|
| `phone1` | Noah Bennett |
| `phone2` | Clara Reed |
| `phone3` | Gabriel Hayes |
| `phone4` | Mina Collins |
| `phone5` | Arthur Clarke |

Use the appropriate username for each client. Each account has its own SIP identity, for example `sip:phone2@192.168.1.118`, with the shared domain and proxy above.

Display names and portraits are examples, not bundled live accounts. A fresh server installation creates accounts with generated passwords; read its administration page for the correct details.

### How to start

Open Linphone and wait for the account to register. Start the server and terminal on the PC as described above.

Administration should list both **term1** and **phone1** under **Registered accounts**. Keep Linphone open during the initial test so the phone can receive calls.

If registration fails, check the credentials, UDP transport, domain, guest Wi-Fi isolation and Windows Firewall. The phone must reach `192.168.1.118`. The address `127.0.0.1:8080` is not a SIP server address for the phone.

### How to use

**Call the terminal from the phone:**

1. Enter **`sip:term1@192.168.1.118`** in Linphone's dial/search field.
2. Start a video call.
3. On the PC's ZmalaCall window, press ENTER.
4. End the call in Linphone, or press ESC/RED on the terminal.

**Receive a call from the terminal:**

1. Keep Linphone open and registered.
2. On the terminal, select **Noah Bennett** (`phone1`) and press ENTER.
3. Answer in Linphone with video enabled.

If calling fails, check that both accounts are registered and the accounts share a group. If a call connects without audio/video, check phone permissions, video enablement, encryption/ICE settings and the selected PC devices.

## Development checks

See [the implementation guide](docs/implementation.md) for module responsibilities, state/lifetime rules and the complete verification commands. Administration source is split into `zmala_server/web/admin-*.js` and `web/styles/`; `admin.js` and `admin.css` are generated assets. Run `npm run build:admin` after editing the sources, or `npm run format` to format and rebuild together. Normal server startup also rebuilds the assets.

Process-control checks use isolated processes and do not stop the live server:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File build_tools/tests/process_controls.ps1
```

With managed terminals stopped, the launcher integration check briefly opens terminal windows, verifies all five CMD scripts and restores the server's initial running/stopped state:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File build_tools/tests/launchers.ps1
```

```powershell
npm.cmd test
& 'C:\msys64\ucrt64\bin\python.exe' -m unittest discover -s zmala_terminal/tests -p 'test_*.py' -v
```

`zmala_terminal/tests/accounts_live.py` provisions temporary accounts and a group, checks real calls with bidirectional audio/video in both directions, exercises the terminal's native video window, removes the group and checks SIP 403 rejection. It deletes its temporary accounts afterwards and leaves the real phone accounts available. Add `--ui-only --video-cycle` to exercise two-press outgoing call confirmation, an initially absent remote video stream, video on/off/resume and continuing audio. `call_feedback_ui.py` checks both call questions, green/red Yes/No prompts, unavailable status, confirmation cancellation, idle-only callback notifications, missed-call badges and missing-video messages in all 95 languages without placing calls. Run with the server running:

```powershell
& 'C:\msys64\ucrt64\bin\python.exe' zmala_terminal/tests/accounts_live.py
```

`zmala_terminal/tests/callbacks_live.py` starts an isolated temporary server and uses the real terminal and Linphone SDK to verify offline request confirmation/cancellation, saved requests, chat delivery on phone registration (including Unicode names), the availability notice, a manually confirmed call and request completion. It also verifies caller cancellation stops ringing, creates a missed-call badge, survives terminal restart and clears when confirmation opens without dialing. Answered and deliberately declined calls are checked for absence of a new badge. It uses unique profiles, static cameras and file audio, and leaves real accounts and the running server untouched. Logs remain under `build_tools/tmp/callback-live-*/`. Server callback tests cover persistence, expiry, duplicate requests, retries, username changes, revoked groups and authenticated API isolation.

`zmala_terminal/tests/terminal_ui_smoke.py` checks registration, pictures, the three-slot carousel, absence of on-screen buttons, connectivity icons and all six screen layouts at two window sizes. Stop the normal terminal before running this check, since each account supports one registration; restart it afterwards. `zmala_terminal/tests/sip_peer.py` and `zmala_terminal/tests/terminal_ui_call.py` are its reusable media-test helpers. Test peers use static cameras and file audio. Results are in `zmala_terminal/data/*-result.json` and `zmala_terminal/data/live-*.log`.

`zmala_terminal/tests/terminal_languages_ui.py` checks all 95 languages in all six display states, including layout at 900×620, countdown updates, carousel motion, the ringing pulse, calling during a transition and changing language during a call. It also verifies the smaller connectivity graphic and absence of the footer and terminal name. It exercises the application's Tk window and Windows text renderer with a quiet engine so it does not register over a real client.

`zmala_terminal/tests/contact_presence_ui.py` checks the large contact status bands in all 95 languages, offline/stale-presence call blocking, live updates without a configuration version change, and cancellation of a pending availability check. It uses a quiet call engine and never places a real call.

`zmala_terminal/tests/provisioning_ui.py` starts an isolated HTTP server and temporary terminal account to check both QR setup steps, real maintenance polling/output, idle-only reset, rejection of held keys, cancellation and reset persistence. It leaves the running server's accounts unchanged. `zmala_terminal/tests/test_provisioning.py` covers QR formats, stale-cache protection and the Windows command runner. Optional PDF/decoder QA uses `zmala_server/tests/generate_setup_qr.cjs`, `zmala_server/tests/render_setup_pdf.cjs` and `zmala_terminal/tests/qr_decode.py`; rendering needs `pdfjs-dist` and `@napi-rs/canvas` installed under `build_tools/runtime/pdf-render/` (prepared on this PC).

`zmala_terminal/tests/qr_decode.py` also exercises repeated QR preview format changes. `zmala_terminal/tests/qr_camera_process.py` takes the same image manifest to check Wi-Fi/server QR readback through the isolated worker, worker shutdown and terminal UI survival after a simulated native camera crash.

## Scope and dependencies

This is a local-network prototype with a Windows or Raspberry Pi server and Windows/Linux terminals, using unencrypted SIP/RTP and a local HTTP management API. It supports one active call and one current registration per account. Media is relayed without recording or transcoding; Windows supports VP8/H.264 and the C20 Raspberry Pi terminal uses H.264. Enable H.264 in Linphone for Pi calls. No WebRTC is used. Room audio, echo and phone behaviour need testing with the actual equipment.

Linux HDMI-CEC wake, input selection and restoration are implemented and tested
on the Pi/Samsung TV. Camera QR provisioning, Windows/Linux maintenance consoles
and Pi installer packages with automatic boot startup are available. See
[Pi recovery and console verification](docs/server-verification.md) for the
live checks and remaining hardware limits. Public Internet hosting, TLS/SRTP,
cross-network NAT tests and managed updates remain later work.

- [Liblinphone SDK](https://www.linphone.org/en/download/) — Windows SDK 5.4.98; retain bundled licence notices (AGPL/commercial dual licensing).
- [SIP transaction/transport stack](https://github.com/kirm/sip.js) — npm `sip` 0.0.6, MIT.
- [Avalonia ANGLE desktop binaries](https://www.nuget.org/packages/Avalonia.Angle.Windows.Natives/2.1.27548.20260419) — retain `build_tools/runtime/angle-desktop/LICENSE`. Bridges built from `build_tools/native/angle_bridge.c` expose the graphics functions to the renderer.
- [Cisco OpenH264](https://github.com/cisco/openh264) — upstream Windows binary 2.2.0; retain applicable upstream notices.
