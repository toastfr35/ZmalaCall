# ZmalaCall implementation overview

This technical guide is for developers and maintainers. It describes component
boundaries, networking, persistent state, build tooling and verification.
[Server implementation](server.md) covers the Node services and deployment;
[terminal implementation](terminal.md) covers state ownership, native media and
Pi hardware integration. Product requirements exist only in
[Doorstop records](../requirements/). [astra.md](../astra.md) tracks engineering gaps.

The separate Word guides are intended for installers, administrators and callers.
Their editable originals live in `docs/`; downloads place them beside the installer
executable. They are not embedded in the executable or installed on the Pi:

- `terminal_prep.docx`: SD image, physical connections and installation.
- `terminal_config.docx`: accounts, enrollment, TV checks and settings.
- `terminal_use.docx`: remote controls, calls, callbacks and everyday help.
- `server_prep.docx`: SD image, installation, migration and first accounts.

Contents: [system](#system-and-supported-hosts), [network](#network-and-identity),
[source/state](#source-and-persistent-state), [development](#development-tools-and-checks),
[requirements workflow](#doorstop-requirements), [distribution](#distribution-and-third-party-components).

## System and supported hosts

ZmalaCall provides a television video-call interface with portrait contacts and
a Microsoft Presenter+ remote. A separate server manages accounts, groups,
settings, SIP signalling and an RTP/RTCP relay. It neither transcodes nor records
calls. Compatible SIP phone clients can participate on the same LAN.

| Component | Current deployment |
| --- | --- |
| Server | Raspberry Pi OS Lite 64-bit, Debian 13 Trixie; installer accepts Pi 3 Model B/B+ and Pi 4 Model B |
| TV terminal | Raspberry Pi 4 Model B, the same OS, Nuroum C20, Presenter+, HDMI TV; Argon ONE Pi 4 V2 fan integration |
| Desktop terminal | 64-bit Windows with Tk/Liblinphone and server-selected camera/audio devices |
| Installers | Windows executables deploying over Ethernet SSH; graphical and headless modes |

Windows server hosting, the serial-keypad project and CAD models are retired.
Other cameras/boards and direct GPIO controls are not established terminal
deployments. Passing portable tests does not qualify a new TV, USB setup or
camera. Sony BRAVIA guidance exists, but physical BRAVIA operation is unverified.

## Network and identity

| Service | Default listener |
| --- | --- |
| Administration and terminal API | TCP 8080, all IPv4 interfaces |
| Optional HTTPS administration | TCP 8443 when certificates are configured |
| SIP | UDP/TCP 5060, all IPv4 interfaces |
| Relayed RTP/RTCP | UDP 20000–20199 |
| Installed Pi SSH | TCP 22, Ethernet only; guard also covers configured sshd ports and IPv6 |

Use a reachable server LAN address and reserve its address in DHCP. A hostname
such as `zmalaserver.local` depends on local name resolution; use its Ethernet IP
when necessary. Loopback on a phone or terminal refers to that device, not the
server. One account has one registration and one call at a time.

The server QR assigns a terminal's device ID and token. The ID is independent of
the Pi hostname and hardware serial. Account association can change without
re-enrollment. Never run two terminals with the same enrollment concurrently.

The current deployment is a trusted-LAN system: SIP/RTP and default HTTP are
unencrypted. Optional HTTPS protects administration, not media. Public-Internet
exposure, SIP TLS/SRTP and cross-network NAT qualification are outside the current
deployment. Installation downloads dependencies; ordinary calls do not download
code or models.

## Source and persistent state

| Path | Purpose |
| --- | --- |
| `zmala_server/` | Node server, administration source, SIP transport and tests |
| `zmala_terminal/common/` | Shared Python controllers, UI, assets, translations and tests |
| `zmala_terminal/windows/` | Windows native loading, rendering, WLAN and process adapters |
| `zmala_terminal/linux/` | Pi adapters, native media, Bluetooth, CEC and peripheral control |
| `build_tools/` | Packaging, installers, launchers, source checks and hardware probes |
| `requirements/` | Doorstop product (`ZMC`), terminal (`TERM`) and server (`SERV`) records |
| `docs/` | Three implementation guides and four Word user guides |

Source launches keep state in component `data/` directories. Pi installations
link those paths to private `/var/lib/zmalacall` or `/var/lib/zmalacall-server`;
root-owned code lives under `/opt/zmalacall/releases` or
`/opt/zmalacall-server/releases`. Do not edit an installed release to store data.
Packages exclude enrollment, account data, private portraits and credentials.
Downloaded SDKs live under `build_tools/runtime`; managed Windows launcher
records live under `build_tools/data`.

## Development tools and checks

From the repository root:

```sh
npm ci
npm --prefix zmala_server ci --ignore-scripts
python -m venv .venv
# Linux:
.venv/bin/python -m pip install -r requirements-dev.txt
# Windows PowerShell:
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
make lint
make test
```

Use GNU Make, a POSIX shell and Cppcheck 2.21 or newer. Windows MSYS2 paths under
`C:/msys64` are detected; PowerShell can invoke Make as
`& C:/msys64/usr/bin/make.exe lint`. Override `PYTHON`, `NODE`, `CPPCHECK` or
`POWERSHELL` on the Make command line, and `LINT_SH` in the environment.

`make lint` checks JavaScript, strict JSDoc/TypeScript contracts, Python, native C,
shell syntax, formatting and generated administration assets. On Windows it also
parses PowerShell scripts. Elsewhere use `make lint-powershell POWERSHELL=pwsh`
when PowerShell is installed. Syntax/static checks do not replace native builds.

`make test` runs the server and portable terminal suites without starting real
terminals. Packaging/installer tests run separately:

```sh
python -m unittest discover -s build_tools/tests -p 'test_*.py'
```

Install `build_tools/windows_installer/requirements.txt` for full installer
coverage. Platform-dependent tests report skips. CI also exercises real renderers
on Windows/Linux, Doorstop validation and Linux native video worker tests against
the Trixie SDK. Live camera, audio, TV and user acceptance remain separate checks.
Run destructive reset/enrollment scenarios with disposable profiles/accounts;
never replace an in-use terminal's SIP registration with a test instance.

Edit `zmala_server/web/admin-*.js` and `web/styles/*.css`, then run
`npm run build:admin`. Do not edit generated `admin.js`/`admin.css` directly.
`npm run typecheck` checks first-party server/browser source; vendored code,
generated bundles and JavaScript fixtures are outside that scope.

### Cleanup

`make clean` removes Python bytecode/cache directories, Ruff/pytest/mypy caches,
root `tmp/`, `requirements/output/`, and `build_tools/tmp/`, `build_tools/dist/` and
`build_tools/.npm-cache/`. Preview with `make clean CLEAN_FLAGS=--dry-run`.
Run after builds/tests finish. Files inside these scratch/output directories,
including diagnostic logs and installer binaries, are disposable. Tracked files
are protected, directory links are not followed, and runtime data, credentials
and dependencies outside those disposable directories are retained.

## Doorstop requirements

The authoritative tree is `ZMC → TERM / SERV` under top-level `requirements/`.
Edit YAML records there; do not copy requirement text into these guides or commit
generated requirement catalogues. Operational examples here describe the
implementation and do not replace the records. `references` paths are relative
to the repository root and point to implementation or verification files.

On Windows, install the pinned runtime with `uv` available, then use the wrapper
which supplies an absolute native project path (relative/forward-slash paths can
break Doorstop's external-reference lookup on Windows):

```powershell
& .\build_tools\install-doorstop.ps1
& .\build_tools\doorstop.cmd --no-reformat --error-all --no-review-check
& .\build_tools\doorstop.cmd add TERM
& .\build_tools\doorstop.cmd edit TERM028
& .\build_tools\doorstop.cmd link TERM028 ZMC005
```

On Linux, in the development environment:

```sh
python -m pip install -r build_tools/doorstop-requirements.txt
doorstop --no-reformat --error-all --no-review-check --project "$PWD"
doorstop add TERM --project "$PWD"
doorstop edit TERM028 --project "$PWD"
doorstop link TERM028 ZMC005 --project "$PWD"
```

Use the ID printed by `add` for a new item; `TERM028` above illustrates editing
an existing item. Structural validation checks levels, references, parent links
and stale parent stamps; `--no-review-check` allows unreviewed items. It does not
claim maintainer acceptance or physical test success. After an actual impact
review, use `doorstop clear <ID>` to accept parent changes and `doorstop review
<ID>` to stamp reviewed text; omit `--no-review-check` for review validation.
Running `doorstop` alone validates the records; it does not render a report.
`publish` writes to the destination supplied on the command line. Optional HTML
reports go in the ignored `requirements/output/` directory:

```sh
doorstop publish all requirements/output --html --project "$PWD"
```

On Windows, the repository wrapper supplies the native absolute project path:

```powershell
& .\build_tools\doorstop.cmd publish all requirements/output --html
```

Open `requirements/output/index.html`. The report includes individual
HTML documents under `documents/` and `traceability.html`/`traceability.csv` at its
root. Generated reports are ignored by Git and removed by `make clean`; the YAML
records under `requirements/` remain the authoritative source.


## Distribution and third-party components

The Windows installer workflows build self-contained executables and perform
GUI/headless smoke tests. Download published assets from the
[latest release](https://github.com/toastfr35/ZmalaCall/releases/latest), or an
artifact from the [workflow runs](https://github.com/toastfr35/ZmalaCall/actions)
for unreleased builds. Artifacts expire after 90 days. The executables are unsigned;
checksums detect transfer corruption, not an untrusted publisher.

Retain bundled licence notices when redistributing:

- Liblinphone Windows SDK 5.4.98 and Linux distribution SDK: AGPL/commercial dual licensing.
- Maintained `sip@0.0.6` copy: MIT; local patches and upstream hashes in
  [ZMALA-PATCH.md](../zmala_server/vendor/sip/ZMALA-PATCH.md).
- Avalonia ANGLE desktop binaries and Cisco OpenH264: retain their upstream notices
  from the downloaded runtime; graphics bridges live in `build_tools/native/`.
- Automatic framing: LiteRT and the SHA-256-pinned SSD MobileNet model; see the
  [terminal processing guide](terminal.md#automatic-framing).
