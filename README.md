# ZmalaCall

ZmalaCall is a television video-call terminal with a portrait carousel and simple
physical controls. A separate server manages accounts, contact groups, settings,
SIP signalling and the audio/video relay. Terminals run on Windows or Raspberry
Pi 4; the server runs on Windows or Raspberry Pi OS. SIP phone clients can join
the same LAN and call permitted contacts.

## Install

Download **`zmala_terminal_setup.exe`** and the illustrated installation guide
from the [latest public release](https://github.com/toastfr35/ZmalaCall/releases/latest).
No GitHub account is required. Release assets include SHA-256 checksums.

- [Pi terminal installation](docs/linux-terminal.md): Raspberry Pi 4, Raspberry
  Pi OS Lite 64-bit Debian Trixie, Nuroum C20 and Microsoft Presenter+ remote.
  The Windows installer checks SSH and the OS, installs dependencies and automatic
  startup, configures the Argon ONE fan and reduces microSD writes. SSH is limited
  to wired Ethernet. GUI and headless installation use the same checks.
- [Pi server installation](docs/pi-server-installation.md): `zmala_server_setup.exe`,
  optional migration of existing server data, automatic startup, Ethernet-only
  SSH and the administration switch for enabling/disabling wired SSH.
- [Administration and password recovery](docs/admin-authentication.md): first
  login, password storage, recovery and optional HTTPS.

Keep private backups of server state, account portraits and terminal enrollment.
Runtime data, credentials, downloaded dependencies and distribution archives are
excluded from Git. The installers contain public application code, not live
accounts or private portraits. Installation needs Internet access for dependencies.

## First terminal startup

On the Pi, setup checks the camera connection, pairs the remote and verifies an
ordered press/release of **left, right, green, red, middle**. It then scans the
Wi-Fi QR code and server QR code. The latter assigns the terminal identity and
credentials; the installer does not hardcode an account. Generate these codes
from the server's administration page.

Installation instructions stay in English until server enrollment supplies the
selected language. After enrollment, localized TV-control checks test standby/
wake and input switching, recording the user's answers. The carousel becomes
available after setup. Reset repeats these checks without deleting server accounts.

## Using the terminal

| Control | Action |
|---|---|
| Left / right | Select a contact; navigate settings or change the selected value |
| Green | Open contact confirmation, confirm a call/request, answer, or accept an edit |
| Red | Cancel, decline or hang up; cancel a selected pending callback request |
| Hold red for 10 seconds on the carousel | Open Settings; progress appears after 2 seconds |
| Hold middle and move up/down | Adjust volume relatively, 2 percentage points per 64 motion units; show a vertical volume bar |

On Windows, Left/Right, Enter and Escape provide the corresponding navigation,
green and red controls. F11 toggles fullscreen outside confirmation. The first
remote press when the TV is off or showing another input restores the terminal
view and is consumed, so it cannot also start a call.

Contact names stay inside their portrait frames. Online/offline bands use both
symbols and words; callback requests and missed calls have distinct badges.
Outgoing calls require a separate green confirmation. An offline contact offers
a callback request instead. Connected calls show the other camera and a small
local self-view; absent incoming video displays an explanation while audio continues.

Settings offers language, automatic answer, automatic framing, speaker volume,
three/five portraits, TV return timeout and Reset. Green opens an editor or
accepts its draft; red discards an edit or leaves. Only the active panel shows
button hints. Confirmed settings are saved through the server; a failed or
conflicting save stays visible for retry.

Automatic answer choices are Never, 10 seconds, 30 seconds, 1, 2, 5 and 10 minutes.
TV return choices are 30 seconds (default), 1, 2, 5, 10, 20 minutes and Never.
Any button activity resets the idle countdown. A thin blue bottom bar appears
after ten seconds without activity; expiry restores the TV state captured when
opening the terminal. Calls and pending settings saves suspend this countdown.

## Server and network

Open `http://<server-address>:8080/`, or `http://zmalaserver.local:8080/` for the
standard Pi installation. On the server machine, `http://127.0.0.1:8080/` also
works. First-time administration sets a password. Accounts owns identities,
credentials, pictures and email addresses; Groups controls who can call whom;
Terminals owns device/display/media settings and the authenticated remote console.

| Service | Default listener |
|---|---|
| HTTP administration and terminal API | TCP 8080, all IPv4 interfaces |
| Optional HTTPS administration | TCP 8443, when certificates are configured |
| SIP signalling | UDP/TCP 5060, all IPv4 interfaces |
| Relayed RTP/RTCP media | UDP 20000–20199 |
| Installed Pi SSH | TCP 22, accepted only through Ethernet |

Use the server's reachable LAN address, account credentials and shared SIP
domain when configuring a phone. `127.0.0.1` on a phone refers to the phone.
Accounts must share a group and register successfully. The current LAN media
setup uses unencrypted SIP/RTP, video enabled and no ICE/STUN. Pi camera calls
use H.264, so enable that codec on the phone. The server relays media without
transcoding or recording; each account supports one registration and one call.
This is not a deployment guide for exposing SIP or administration to the Internet.

Each terminal has independent 480p, 720p or 1080p video and a target of 10, 15,
20, 25 or 30 fps. Fresh defaults are **720p at 15 fps**. Sending bandwidth scales
with resolution and target rate; receiving capacity is independent of the local
target. Targets are not guaranteed delivered frame rates. Changes that rebuild
the media graph wait until idle. See [Pi video evidence](docs/pi-hardware-video.md)
and [automatic framing](docs/automatic-framing.md) for measured limits and processing.

## Run from a Windows checkout

```powershell
git clone https://github.com/toastfr35/ZmalaCall.git
Set-Location ZmalaCall
npm.cmd ci
npm.cmd --prefix zmala_server ci --ignore-scripts
```

Use the root **Start ZmalaCall Server.cmd** and **Start ZmalaCall Terminal.cmd**
launchers independently. Runtime setup scripts prepare the required dependencies.
**Start ZmalaCall Terminal Unconfigured.cmd** uses a separate enrollment profile;
pass `-ConnectWifi` to join the scanned network instead of testing the existing
link, and `-Fullscreen` for fullscreen. The regular terminal also accepts
`-Fullscreen`; the server accepts `-NoBrowser`.

The matching **Stop** launchers stop only their recorded component processes.
They do not erase configuration or stop directly launched Python/Node instances.
Do not run two instances with the same terminal account: registration is exclusive.
See the [implementation guide](docs/implementation.md) for entry points, native
runtime dependencies, isolated integration tests and process ownership.

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

## Documentation and scope

- [Design and behavior](docs/design.md)
- [Implementation and verification](docs/implementation.md)
- [Requirements source and generated catalogues](docs/README.md)
- [Persistence and recovery limits](docs/reliability.md)
- [Review findings and follow-up work](astra.md)

Linux HDMI-CEC, camera enrollment, Bluetooth onboarding, Windows/Linux consoles
and boot services are implemented. TV compatibility, room acoustics, USB power
stability and delivered video quality still require the actual hardware. Dated
hardware reports describe the setup measured at that time; they are not universal
performance guarantees. Managed updates, SIP TLS/SRTP and cross-network NAT
qualification remain separate work.

- [Liblinphone SDK](https://www.linphone.org/en/download/) — Windows SDK 5.4.98; retain bundled licence notices (AGPL/commercial dual licensing).
- [SIP transaction/transport stack](https://github.com/kirm/sip.js) — npm `sip` 0.0.6, MIT.
- [Avalonia ANGLE desktop binaries](https://www.nuget.org/packages/Avalonia.Angle.Windows.Natives/2.1.27548.20260419) — retain `build_tools/runtime/angle-desktop/LICENSE`. Bridges built from `build_tools/native/angle_bridge.c` expose the graphics functions to the renderer.
- [Cisco OpenH264](https://github.com/cisco/openh264) — upstream Windows binary 2.2.0; retain applicable upstream notices.
