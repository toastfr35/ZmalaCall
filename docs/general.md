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
| `requirements/` | Doorstop product (`PROD`), server (`SHLR`/`SLLR`) and Pi terminal (`THLR`/`TLLR`) records |
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

The implementation baseline has five documents:

```text
PROD  Product specification
├── SHLR  Server high-level requirements
│   └── SLLR  Server low-level requirements
└── THLR  Pi terminal high-level requirements
    └── TLLR  Pi terminal low-level requirements
```

The YAML records under `requirements/` are authoritative. HLRs link to product
items; LLRs link to their component HLRs and reference implementation and test
files relative to the repository root. `area` groups related behavior, `scope`
distinguishes Core/Optional/Experimental, and `verification` describes a proposed
check, not its result. Review stamps cover these fields as well as requirement
text. The scope includes the Linux server, shared/Pi terminal implementation and
Pi installation tooling, including the Windows installer front ends. Windows
terminal runtime and retired keypad/CAD work are outside this baseline.

### Validate and publish

Install the pinned tooling into the development environment:

```sh
python -m pip install -r build_tools/doorstop-requirements.txt
make requirements-check
make requirements
```

Alternatively, Windows can use the dedicated managed runtime (`uv` required):

```powershell
& .\build_tools\install-doorstop.ps1
& .\build_tools\runtime\doorstop\Scripts\python.exe build_tools/requirements.py
```

`make requirements` automatically prefers that dedicated Windows runtime when
present; otherwise it uses the Makefile's `PYTHON`. Override with
`REQUIREMENTS_PYTHON=...` when needed. Both routes supply an absolute native project
path because forward-slash project paths can break Doorstop reference lookup on
Windows.

The build checks the five-document hierarchy, required fields, component-specific
parent links, leaf implementation references and mapping of every in-scope source
module, plus a code comment anchor for every LLR. Its inventory also lists excluded
generated bundles, test/probe code and
third-party internals with reasons. Mapping a file is a maintenance aid, not proof
that every behavior or hardware scenario has been verified. When changing a module,
review its mapped LLRs and parents; when adding one, add or extend the corresponding
LLR. Do not satisfy coverage with an unrelated reference.

Open `requirements/output/index.html`. The offline report includes searchable
requirement cards, document navigation, parent/child links, verification guidance,
a traceability table/CSV and source coverage HTML/JSON with code file/line anchors.
It works without a web
server or external CDN. JavaScript only adds search. The native Doorstop template
lives in `requirements/product/template/`; `build_tools/requirements.py` adds the
inventory and validates the generated links. GitHub Verify uploads the complete
folder as `zmala-requirements`. Extract the artifact before opening `index.html`.
Generated output is ignored by Git and removed by `make clean`.

### Edit and review

Use Doorstop or edit YAML directly. Examples on Linux (activate the tooling
environment first):

```sh
doorstop add TLLR --project "$PWD"
doorstop edit TLLR094 --project "$PWD"
doorstop link TLLR094 THLR016 --project "$PWD"
```

On Windows use `build_tools\doorstop.cmd` with the same subcommands; the wrapper
supplies the native project path. Use the ID printed by `add` for new items; the
other commands above illustrate an existing runtime TV requirement. Supply its
header, normative text, area, scope, verification guidance and source references.
Keep IDs stable once issued; do not renumber them to reorder a document.

### Code trace comments

Put a standalone `@llr` comment immediately before the function, declaration or
cohesive block that implements the requirement. Use the language's comment syntax:

```python
# @llr TLLR014
def move(self, dy):
    ...
```

```javascript
// @llr SLLR028
```

Use `# @llr SLLR098, TLLR124` for shared Python/shell/configuration policies,
`// @llr TLLR055` for C, `/* @llr SLLR057 */` for CSS, and
`<!-- @llr SLLR056 -->` for HTML. Multiple IDs use a comma and one space. Keep
explanatory prose in a separate comment; the directive contains only IDs. Put it
before Python decorators or JavaScript JSDoc so those stay attached to the declaration.

Each LLR has at least one implementation anchor; behavior spread across modules
can have several. The anchored file must also appear in that LLR's Doorstop
`references`. Keep both directions in sync when moving code. Choose the code that
enforces the behavior, rather than collecting IDs at the top of an unrelated
module. Trace JSON data at the code that validates or consumes it. Add markers
only to authored implementation or explicitly referenced local vendor patches,
never generated bundles or tests. Regenerate admin bundles after source edits.

`build_tools/requirements_trace.py` reads these directives during both requirements
targets and CI. It rejects unknown IDs, malformed directives, unreferenced anchor
files and LLRs without code anchors. Python markers are read from comment tokens;
other formats use reserved full-line comment syntax, so do not copy directive
lines into string/heredoc literals. These checks do not interpret conditional
compilation or prove behavior. Review placement and verification evidence separately.

Each rendered LLR links to its current file/line locations in the source coverage
page. `coverage.json` exposes the same locations under `code_traces`, keyed by
LLR ID. Lines are computed at build time, not maintained manually in YAML.

### Review status

The old ZMC/SERV/TERM baseline was replaced because it mixed abstraction levels
and included Windows terminal/retired keypad scope. Historical records remain in
Git; new links use PROD/SHLR/SLLR/THLR/TLLR.

Structural checks use `--no-review-check` to permit a baseline awaiting human
review. They still check references and suspect parent links. After an actual
impact review, `doorstop clear <ID>` accepts a changed parent stamp; after reviewing
the requirement, `doorstop review <ID>` stamps it. Neither operation records a
passed test. Omit `--no-review-check` when validating review completion. Initial
records are intentionally not marked human-reviewed.

Running `doorstop` alone validates; it does not render. For just the native HTML
(without the source inventory), use `doorstop publish all requirements/output
--html --template zmala --project "$PWD"`. Prefer `make requirements` for the complete
report and all checks. Technical guides explain implementation and workflows;
normative requirements belong only in the Doorstop records.


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
