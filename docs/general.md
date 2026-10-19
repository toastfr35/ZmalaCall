# ZmalaCall implementation overview

This technical guide is for developers and maintainers. It describes component
boundaries, networking, persistent state, build tooling and verification.
[Server implementation](server.md) covers the Node services and deployment;
[terminal implementation](terminal.md) covers state ownership, native media and
Pi hardware integration. [Android implementation](android.md) covers ZmalaPhone. Product requirements exist only in
[Doorstop records](../requirements/). [astra.md](../astra.md) tracks engineering gaps.

The Pi and Android SDK adapters share the bounded TURN TLS write helper under
`zmala_terminal/common/native/`; each adapter is pinned to its SDK's native ABI.

The release PDFs are intended for installers, administrators and callers.
Their editable Word originals live in `docs/`; PDFs sit beside the installers.
They are not embedded in the executable or installed on the Pi:

- `terminal_prep.docx`: SD image, physical connections and installation.
- `terminal_config.docx`: accounts, enrollment, TV checks and settings.
- `terminal_use.docx`: remote controls, calls, callbacks and everyday help.
- `server_prep.docx`: SD image, installation, migration and first accounts.
- `phone_installation.docx` and `phone_guide.docx`: Android installation and everyday use.

`build_tools/update-release-guides.py` maintains the download instructions and
phone authoring content. `build_tools/release/guides.py` renders all six PDFs:
terminal configuration and use form one Guide; server preparation is split into
Installation and Guide. The Word files remain editable sources, not release assets.

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
| Android app | ZmalaPhone LAN or encrypted relay video with Firebase incoming alerts, Android 9+, Linphone SDK 5.5.32 |
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
| Optional HTTPS administration | TCP 8443 when certificates are configured; administration restricted to the server LAN |
| SIP | UDP/TCP 5060, all IPv4 interfaces |
| Relayed RTP/RTCP | UDP 20000–20199 |
| Installed Pi SSH | TCP 22, Ethernet only; guard also covers configured sshd ports and IPv6 |

Use a reachable server LAN address and reserve its address in DHCP. A hostname
such as `zmalaserver.local` depends on local name resolution; use its Ethernet IP
when necessary. Loopback on a phone or terminal refers to that device, not the
server. One account has one registration and one call at a time.

Server QR codes assign a device ID and token. App codes carry `account_type: app` and use a separate app configuration API. App and Terminal are exclusive account types; converting between them rotates enrollment and SIP credentials. A terminal QR assigns a terminal's device ID and token. The ID is independent of
the Pi hostname and hardware serial. Account association can change without
re-enrollment. Never run two terminals with the same enrollment concurrently.

The default deployment is a trusted-LAN system: SIP/RTP and default HTTP are
unencrypted. Optional HTTPS alone protects administration, not media. The explicit
secure relay deployment adds SIP TLS, mandatory SRTP and TURN TLS for networks
that block UDP; see [server setup](server.md#secure-calls-when-a-terminal-network-blocks-udp).
It needs public TLS endpoints and separate relay provisioning. Installation downloads
dependencies; ordinary calls do not download code or models.

## Source and persistent state

| Path | Purpose |
| --- | --- |
| `zmala_server/` | Node server, administration source and SIP transport |
| `zmala_terminal/common/` | Shared Python controllers, UI, assets and translations |
| `tests/server/{LLT,HLT}/` | Server unit and system/integration test plans and implementations |
| `tests/terminal/{LLT,HLT}/` | Pi terminal unit and system/integration test plans and implementations |
| `tests/support/` | Shared fixtures and runners; no independent requirement coverage |
| `tests/adhoc/` | Exploratory probes, tooling regressions and Windows compatibility checks |
| `zmala_terminal/windows/` | Windows native loading, rendering, WLAN and process adapters |
| `zmala_terminal/linux/` | Pi adapters, native media, Bluetooth, CEC and peripheral control |
| `build_tools/` | Packaging, installers, launchers, source checks and hardware probes |
| `requirements/` | Doorstop product (`PROD`), themed server (`*-SRV-*`), Pi terminal (`*-TERM-*`) and Android (`*-AND-*`) records |
| `docs/` | Four implementation guides and four Word user guides |

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

`make test` runs both levels of portable requirement-based tests for the Pi
server and terminal. It does not start deployed terminals, operate a TV or place
live calls. Run levels independently or check development tooling with:

```sh
make test-llt
make test-hlt
# Linux display scenarios (including standalone scripts outside unittest discovery):
xvfb-run -a make test-hlt test-hlt-display
make test-adhoc
make requirements
```

Install `build_tools/windows_installer/requirements.txt` for full installer
coverage. Install headless Chromium with `npx playwright install chromium`
(on Linux CI use `npx playwright install --with-deps chromium`) for the isolated
admin layout tests. `test-hlt-display` selects only standalone tests marked
`display`, redirects mutable terminal profiles to a temporary directory, and
fails if Linux has no display. It never selects hardware/native entry points.
The exhaustive layout scenarios cover 95 languages and can take several minutes.
Platform-dependent tests report skips. CI also exercises real renderers
on Windows/Linux, Doorstop validation and Linux native video worker tests against
the Trixie SDK. Live camera, audio, TV and user acceptance remain separate checks.
Run destructive reset/enrollment scenarios with disposable profiles/accounts;
never replace an in-use terminal's SIP registration with a test instance.

### Requirement-based test plans and traces

Execution coverage is separate from the traceability report. `make coverage-llt`
runs only server and terminal LLTs and writes `tests/coverage/LLT/index.html`,
with separate JavaScript, Python and native reports, machine-readable summaries,
and `gaps.json` listing missing lines/functions and their LLR references. It never
merges HLT or ad-hoc execution into LLT totals. Unimported authored files remain
in the denominator. `make coverage-check` runs the same measurement and fails
unless functions and statements reach 100% and no executable source is unmeasured.
The initial baseline is below that target; a successful reporting command does
not mean the target passed. Tool self-tests under `tests/adhoc/tooling/` validate
counter aggregation but do not contribute product coverage.

JavaScript uses Istanbul counters for server modules and authored browser modules,
including VM-based unit tests and Playwright page navigation. Generated bundles,
dependencies and upstream vendor code are excluded. Python uses coverage.py's
executable-line statement metric and named function body regions, with runtime
and Linux host-policy helpers selected from the requirement source inventory.
Installer and packaging code is excluded from both the requirements and RBT coverage.
Windows terminal implementation is outside the Pi baseline. Python reports retain
the execution platform and skip counts. Function entry and statement execution
do not establish that assertions check every required outcome.

Run the Python suites on Linux under `xvfb-run -a` to exercise real Tk widgets
and Cairo/Pango rendering without a physical display. LLTs replace external
SSH, Bluetooth, USB, CEC, process and network boundaries with controlled doubles;
they retain the production state machines, queues, parsing and ownership logic.
Native failure-injection tests exercise codec, scaler and device errors without
opening a camera or changing the running terminal. Hardware timing and acoustic
quality still require separate HLT evidence.

Native coverage runs on Linux with the normal SDK/compiler prerequisites:

```sh
ZMALA_NATIVE_COVERAGE_DIR="$PWD/tests/coverage/LLT/terminal/native" sh tests/support/terminal/run-native.sh
python3 build_tools/rbt_coverage.py --report-only
```

This adds GCC instrumentation to the native LLTs and compiles zero-hit
baseline objects for all authored native translation units. gcov executable-line
and function-entry results remain separate from JavaScript/Python percentages.
Run it after `make coverage-llt`, which starts a fresh report. Compiler data is
retained inside the report directory; `make clean` removes it. Shell and Plymouth
script execution is currently listed as unmeasured, never silently counted as
covered. HTML/JSON and execution logs are available in the CI coverage artifact.

Coverage instrumentation is confined to the test processes and scratch builds;
the installed applications and generated production admin bundle are unchanged.

Focused unit fixtures include recording Tk widgets for display state/geometry
(`T-LLT-053`) and a recording DOM/API for callback and SMTP editors (`S-LLT-030`).
Installer regression suites separately use a virtual clock and SSH/SFTP doubles
under `tests/adhoc/`; they do not contribute to these LLT measurements.
The native echo-rate suite (`T-LLT-054`) uses a real MediaStreamer factory with a
recording DSP child, without opening audio devices. These fixtures verify policy,
arguments and lifecycle behavior; physical rendering, actual SMTP delivery,
post-install hardware readiness and audible quality remain system checks.

Test effectiveness is assessed separately from execution coverage: a scenario
needs an observable expected result, realistic inputs, and assertions that reject
plausible violations of its linked requirement. Review error type/status and
unchanged-state assertions as well as success results. Mock external boundaries;
keep the policy being verified real. Source-text checks establish configuration
contracts only, not live hardware behavior. This follows the distinction in
[Google's coverage guidance](https://testing.googleblog.com/2020/08/code-coverage-best-practices.html)
between executing code and checking its outcomes.

`python tests/adhoc/tooling/mutation_spotcheck.py` checks a small, explicit set of
backup and volume faults against their LLTs. It compiles mutations only inside
child processes, requires a passing baseline and assertion failures, and saves
results under `tests/coverage/review/`. This is a sampled assertion audit, not a
whole-project mutation score, and contributes no execution hits to RBT coverage.

Each LLT/HLT file is a stable, named verification scenario or suite. Its named
assertion cases implement the plan at the top of the file; unrelated scenarios
belong in separate files. LLTs isolate units/components using controlled inputs,
temporary storage and doubles for external dependencies. HLTs exercise assembled
behavior through HTTP, SIP, processes, the actual UI renderer or physical devices.
Mixed files are split when the assertion cases belong at different levels.

Python/shell test headers use `#`; JavaScript/C use `//`. Headers precede imports,
docstrings and executable code (a shebang may precede them). Example:

```python
# @test T-LLT-041
# @requirements LLR-TERM-REMOTE-016, LLR-TERM-AUDIO-006, LLR-TERM-AUDIO-007, LLR-TERM-AUDIO-008
# @environment portable
# @plan Feed signed motion around deadband and limits while holding/releasing middle; assert relative volume increments, throttled mixer writes, overlay lifetime, default changes and retry after failed writes.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.
```

Test IDs use `S-LLT-NNN`, `S-HLT-NNN`, `T-LLT-NNN` or `T-HLT-NNN`; retain IDs
when renaming files and never reuse retired IDs. Assign the next unused number
for a new scenario. LLTs link directly to one or more component LLRs; HLTs link
directly to component HLRs. Multiple independent test plans can exercise different
parts of a requirement. Add the test file to each linked Doorstop item's
`references`, alongside implementation references for LLRs. Do not infer a test
link merely because it imports a source file or exercises a child requirement.

The plan states the setup/input, actions and expected observations actually
checked. Keep the scope narrower than the requirement when the test is partial.
The environment is one of `portable`, `display`, `native-sdk`, `native-display`,
`hardware` or `linux-root`. Nonportable scenarios are explicit entry points; read
their arguments and setup instructions before running. A header is a plan, not
proof that the scenario ran. Record the revision, test ID, command, platform,
result and any skipped cases or manual observations with execution evidence.

`build_tools/test_trace.py`, called by `make requirements`, rejects missing plans,
malformed or duplicate IDs, unknown requirements, wrong levels/components,
nonreciprocal links, any LLR without a direct LLT, any HLR without a direct HLT,
and tests that drift outside `tests/`. Adding a requirement requires adding its
checks in the same change. The report's **Tests**
page (`requirements/output/tests.html`, with `tests.json`) shows the requirement
to test matrix, full plans and requirements with no mapped test. A linked test
does not imply complete requirement coverage; a skip is not a pass. Opt-in
installed-host and reboot tests remain unqualified until run on their target. Review the
assertions against each requirement, including boundary and failure behavior.

The root-only SSH HLTs run in disposable network namespaces, never in the host
firewall. They verify Ethernet and Wi-Fi ingress with IPv4/IPv6, including Wi-Fi
packets addressed to the Ethernet IP. Run them with `sudo python -m unittest
tests.server.HLT.test_ssh_guard_linux tests.terminal.HLT.test_ssh_guard_linux`.
They need `iproute2` and `nftables`; CI runs this step explicitly so a non-root
skip cannot stand in for firewall verification.

New product regressions belong in LLT/HLT. `tests/adhoc/` is for non-RBT work,
including development-tool self-tests and Windows-only terminal compatibility
outside the Pi baseline. Its maintained `test_*.py` and `*.test.js` checks run via
`make test-adhoc`; manual/live probes never run automatically. Keep private local
experiments and evidence in ignored `tests/adhoc/tmp/`, removed by `make clean`.
Shared fixtures in `tests/support/` have no test IDs or independent coverage.

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

Requirements are grouped by component and theme. The catalogue in
`requirements/groups.json` names each group; each has a Doorstop HLR document
and a child LLR document. For example:

```text
PROD  Product specification
├── HLR-SRV-MEDIA       Server media relay outcomes
│   └── LLR-SRV-MEDIA   Server media relay contracts
└── HLR-TERM-VIDEO      Terminal video and framing outcomes
    └── LLR-TERM-VIDEO  Terminal video implementation contracts
```

IDs use `<HLR|LLR>-<SRV|TERM|AND>-<GROUP>-NNN`, for example
`LLR-TERM-VIDEO-012`. The three-digit number is unique across **both HLRs and
LLRs in the same component/theme**: `HLR-TERM-VIDEO-012` cannot coexist with
`LLR-TERM-VIDEO-012`. Other component/theme groups have independent sequences.
Product IDs remain `PROD001` etc.; LLT/HLT test IDs are unchanged.

Folders follow `requirements/<server|terminal>/<theme>/<hlr|llr>/`.
The migration lookup in `requirements/id-migration.json` preserves the old-to-new
ID correspondence; old IDs are no longer accepted in code/test trace comments.
The component rewrites also keep complete one-to-many successors in
`requirements/terminal/migration.json` and `requirements/server/migration.json`.
The flat legacy lookup selects a primary successor; use the complete map when reviewing a split requirement. Retired IDs
remain historical identities and are not reused. Descriptive overviews are in
[terminal.md](terminal.md#terminal-purpose-and-functions) and
[server.md](server.md#server-purpose-and-functions).
Use the report's themed navigation to browse the HLR and LLR documents together.

The YAML records under `requirements/` are authoritative. HLRs link to product
items; LLRs link to HLRs in their component/theme and reference implementation and test
files relative to the repository root. `area` identifies a narrower topic within the theme, `scope`
distinguishes Core/Optional/Experimental, and `verification` describes a proposed
check, not its result. Review stamps cover these fields as well as requirement
text. The scope includes the Raspberry Pi server, shared/Pi terminal runtime and
their Linux host policies. Installers, packaging and deployment verification are
outside the requirements baseline, as are the Windows terminal runtime and retired
keypad/CAD work. Installer regression tests remain under
`tests/adhoc/server_installer/` and `tests/adhoc/terminal_installer/`, run in CI,
and do not contribute to requirement-based test coverage.

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

The build checks the themed hierarchy, shared group-number uniqueness, required
fields, component/theme-specific parent links, leaf implementation references and mapping of every in-scope source
module, plus a code comment anchor for every LLR. Its inventory also lists excluded
generated bundles, test/probe code and
third-party internals with reasons. Mapping a file is a maintenance aid, not proof
that every behavior or hardware scenario has been verified. When changing a module,
review its mapped LLRs and parents; when adding one, add or extend the corresponding
LLR. Do not satisfy coverage with an unrelated reference.

Open `requirements/output/index.html`. The offline report includes searchable
requirement cards, document navigation, parent/child links, verification guidance,
a traceability table/CSV, source coverage HTML/JSON with code file/line anchors,
and a bidirectional test-plan matrix with explicit coverage gaps.
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
python build_tools/requirements.py --next-id LLR TERM TV
# Use the printed number with the matching document; example only:
doorstop add LLR-TERM-TV --number 033 --project "$PWD"
doorstop edit LLR-TERM-TV-027 --project "$PWD"
doorstop link LLR-TERM-TV-027 HLR-TERM-TV-018 --project "$PWD"
```

On Windows use `build_tools\doorstop.cmd` with the same subcommands; the wrapper
supplies the native project path. Use `--next-id` before `add` and pass its numeric suffix explicitly: Doorstop
otherwise allocates within one level and could reuse an HLR number. The suggested
ID is not reserved; concurrent changes must recheck before merging.
Use the ID printed by `add` for new items; the
other commands above illustrate an existing runtime TV requirement. Supply its
header, normative text, area, scope, verification guidance and source references.
Keep IDs stable once issued; do not renumber them to reorder a document.

### Code trace comments

Put a standalone `@llr` comment immediately before the function, declaration or
cohesive block that implements the requirement. Use the language's comment syntax:

```python
# @llr LLR-TERM-REMOTE-016
def move(self, dy):
    ...
```

```javascript
// @llr LLR-SRV-CALL-004
```

Use `# @llr LLR-SRV-HOST-003, LLR-TERM-NET-006` for shared Python/shell/configuration policies,
`// @llr LLR-TERM-VIDEO-010` for C, `/* @llr LLR-SRV-UI-013 */` for CSS, and
`<!-- @llr LLR-SRV-UI-012 -->` for HTML. Multiple IDs use a comma and one space. Keep
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
Git. The subsequent theme migration preserves the implementation-derived content
and parent relationships while replacing the flat component IDs. New links use
`PRODNNN`, `HLR-<component>-<theme>-NNN` and `LLR-<component>-<theme>-NNN`.

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


## Three-network Docker lab

`tests/support/network_lab/` runs the server and two terminal call engines in
Debian Trixie containers. Three separate LANs connect through three Linux NAT
routers to an isolated simulated Internet. Each terminal sends through its own
router. The server router forwards TCP 8080 and UDP 5060/20000–20199. Client UDP
source ports are translated to 40000–49999. No port is published on Windows or
the real LAN, and the fixture creates disposable accounts instead of copying
installed server data.

On this PC, Docker Engine and Compose run inside the existing Ubuntu-24.04 WSL2
distribution. From the repository, use these PowerShell commands:

```powershell
wsl -d Ubuntu-24.04 -u root --cd /mnt/w/git/zmala -- python3 tests/support/network_lab/lab.py build
wsl -d Ubuntu-24.04 -u root --cd /mnt/w/git/zmala -- python3 tests/server/HLT/network_lab.py
wsl -d Ubuntu-24.04 -u root --cd /mnt/w/git/zmala -- python3 tests/support/network_lab/lab.py status
wsl -d Ubuntu-24.04 -u root --cd /mnt/w/git/zmala -- python3 tests/support/network_lab/lab.py down
```

The terminal entry point is `tests/terminal/HLT/network_lab.py`; both entry points
run the same combined scenario, so run only one at a time. Build after production
source changes. Helper files are mounted read-only and do not require a rebuild.
Reports appear in `tests/coverage/network-lab/index.html`, with measurements in
`results.json` and container/router logs alongside. `down` removes this project's
containers, networks, disposable credentials and its scoped bridge firewall
rules. It leaves Docker and the reusable image installed.
For interactive work between commands, keep a WSL shell open: this PC can stop
the WSL VM after its last Windows-launched WSL process exits. The test command
keeps its session alive for the whole run. Start with the runner again after a
VM shutdown; do not treat saved container state as a running lab.

The runner needs root within WSL for the lab's `DOCKER-USER` rules. These rules
allow frames within each lab bridge to reach the simulated routers; they do not
allow traffic between bridges or to the physical network. The router containers
need `NET_ADMIN` for NAT and controlled loss, delay and rate limits. Container
control uses `docker exec` and a loopback HTTP endpoint; call traffic must cross
the routers. A direct-private-address failure check detects bypass paths.

Plans S-HLT-029 and T-HLT-032 check registration, authenticated configuration,
calls in both directions, decoded opposite-frequency audio, decoded H.264 video,
an idle interval, impaired transport, blocked media and recovery. The shared
terminal Engine, Liblinphone and production video decoder execute normally.
Synthetic pictures and WAV tones replace physical capture/playback, and OpenH264
replaces the Pi-only V4L2 encoder. This is partial protocol qualification, not a
Pi performance, C20, local-preview, Bluetooth or TV test. It does not qualify
arbitrary NAT implementations, SIP ALGs, restrictive institutional firewalls,
public-service security, TLS/SRTP or TURN support.
The static test source can run at about one frame per second despite the configured
15 fps target. Decoder activity is sampled continuously with the terminal's normal
four-second freshness window. The scenario is not a 1080p bandwidth or capacity
benchmark. The impairment case adds 80 ms delay, 20 ms jitter, 1% loss and a
3 Mbit/s limit on home A's WAN egress; the low-rate picture does not saturate it.

For the explicit UDP-denied matrix, append `--udp-blocked` to either HLT entry
point. This mode first verifies calls without a fault. It then drops all forwarded
UDP at home A and at home B separately, starts fresh server/client processes, and
checks that HTTP configuration still works while SIP registration and calls fail.
The fixture uses the server's numeric address, so DNS blocking cannot explain
the observed SIP failure.
The blocked caller is observed for 40 seconds, with firewall counters proving that
packets reached the deny rule. It also blocks only UDP media ports 20000–20199 at
each home and calls in both directions: SIP must connect while decoded video and
received audio remain absent. Each unblock is followed by a decoded-media recovery
call. Recording files are removed before each capture because the SDK can append
to an existing WAV after a client restart. A passed negative test means the predicted failure was reproduced, not that
ZmalaCall supports UDP-blocked networks. The report is written separately to
`tests/coverage/network-lab/udp-blocked/index.html`. No live Pi firewall is changed.

## Distribution and third-party components

The release workflow builds self-contained Windows executables and performs
GUI/headless smoke tests. Download published assets from the
[latest release](https://github.com/toastfr35/ZmalaCall/releases/latest), or an
artifact from the [workflow runs](https://github.com/toastfr35/ZmalaCall/actions)
for build inspection. Release artifacts expire after seven days. The executables are unsigned;
checksums detect transfer corruption, not an untrusted publisher.

### Release download layout

Upload exactly these nine files as release assets:

| Component | Installation | User guide | Installer |
| --- | --- | --- | --- |
| Terminal | `ZmalaTerminal-Installation.pdf` | `ZmalaTerminal-Guide.pdf` | `ZmalaTerminal-Pi4-setup.exe` |
| Server | `ZmalaServer-Installation.pdf` | `ZmalaServer-Guide.pdf` | `ZmalaServer-Pi4-setup.exe` |
| Phone | `ZmalaPhone-Installation.pdf` | `ZmalaPhone-Guide.pdf` | `ZmalaPhone.apk` |

Build both Windows installers from the intended committed source, then render
the guides using `python build_tools/release/guides.py` with dependencies from
`build_tools/release/requirements.txt`. Build and verify the signed APK using
`build_tools/android/release.py`. Finally run:

```sh
python build_tools/release/assemble.py --apk build_tools/dist/ZmalaPhone-0.3.6/ZmalaPhone.apk --output build_tools/dist/release-downloads
```

Use a new output directory for each collection. The collector validates every input
before copying and uses an explicit allowlist: no source packages, DOCX files,
checksums, signing files or account QR codes are uploaded as additional assets.
Put SHA-256 checksums, version/build provenance, license notices and corresponding
source links in the release description. GitHub adds its own source ZIP/tar links;
these are generated by GitHub, not uploaded by this tooling.

The AGPL SDK's corresponding-source and notice obligations still apply when
no source archive is attached. Verify complete, version-matched source access
(including SDK dependencies and local changes) before publishing binaries.
A repository ZIP alone does not include the external SDK sources. Source access
may be provided through versioned source repositories linked from the release;
see `zmala_phone/NOTICE.md`.

### GitHub Actions publication

Work is tracked in issues and pull requests. **Verify** runs for pull requests
targeting `main` (or by manual dispatch), cancelling superseded runs for the same
pull request. It does not also run on branch pushes. Its version check requires
both Android version fields to increase above the PR base and the proposed tag
to be unused. Protected `main` requires up-to-date passing platform checks and
a pull request; each change, including documentation, carries a version bump.

**Publish release** (`.github/workflows/release.yml`) starts on each merge into
`main`. The tag comes from the committed Android version. Manual dispatch on
`main` remains available for recovery, with an optional matching tag check.
Windows builds both Pi installers and all PDFs; Linux builds and verifies the
signed APK. The publication job waits for both, collects the nine named files,
creates a draft, uploads and checks its assets, then publishes it. GitHub selects
Latest using its semantic-version policy, so an older overlapping build does not
explicitly replace a newer release. Concurrency is scoped to the source commit;
separate merged commits are not cancelled. The old standalone installer workflows
are removed; their packaging checks are retained in Verify and the release build.
The Android artifact may retain its version directory. The collector accepts that
artifact root and requires exactly one `ZmalaPhone.apk`; ambiguous APK inputs fail.
Existing releases are never overwritten. A failed upload leaves a draft for review.
Inspect and remove only the failed unpublished draft/tag before rerunning that
commit's workflow. Re-running an already published release fails without replacing it.

Configure these repository **Actions secrets**, never repository files:

- `ZMALA_ANDROID_KEYSTORE_BASE64`: base64 of the existing release PKCS12 keystore.
- `ZMALA_ANDROID_SIGNING_JSON`: `storePassword`, `keyAlias`, `keyPassword` and
  `certificateSha256` from the private release configuration; the runner supplies
  `storeFile` itself.
- `ZMALA_FIREBASE_CLIENT_JSON`: the app's `google-services.json` content.

The sender service-account key is not used by Android and must not be uploaded.
Only the Android job receives these secrets. It writes mode-0600 temporary files,
verifies the resulting signing certificate and removes the files even on failure.
Signing files, Firebase JSON and build logs are excluded from uploaded artifacts.
The public Firebase client identifiers remain inside the APK by design. The
`GITHUB_TOKEN` has write access only in the publish job. Keep the private signing
key backup independently; GitHub does not let operators retrieve stored secrets.

Retain bundled licence notices when redistributing:

- Liblinphone Windows SDK 5.4.98 and Linux distribution SDK: AGPL/commercial dual licensing.
- Maintained `sip@0.0.6` copy: MIT; local patches and upstream hashes in
  [ZMALA-PATCH.md](../zmala_server/vendor/sip/ZMALA-PATCH.md).
- Avalonia ANGLE desktop binaries and Cisco OpenH264: retain their upstream notices
  from the downloaded runtime; graphics bridges live in `build_tools/native/`.
- Automatic framing: LiteRT and the SHA-256-pinned SSD MobileNet model; see the
  [terminal processing guide](terminal.md#automatic-framing).


## Secure network verification

Run `sudo python3 -m tests.server.HLT.secure_network_lab` from the WSL checkout after
`python3 tests/support/network_lab/lab.py build`. The terminal counterpart is
`tests.terminal.HLT.secure_network_lab`; both execute one shared matrix, so do not
run them concurrently. This is requirement-based verification of the application
secure mode, not a production transport monkeypatch. Reports are saved under
`tests/coverage/network-lab/tls/`. The matrix tests eight call cases across four
UDP policies, decoded opposite audio tones, fresh H.264 frames, native SRTP/relay
state, certificate probes and firewall counters. Static media and software encoding
do not qualify physical C20 quality or Pi throughput. Clean up with
`ZMALA_LAB_TLS=1 python3 tests/support/network_lab/lab.py down`.

The parser LLT is built by `build_tools/linux/build-turn.py`; it runs both the known
bad upstream implementation and the corrected implementation as a negative/positive
control. Generated binaries, downloaded SDK sources and reports stay out of Git.
Portable unit tests validate policy, temporary credentials, SDP rejection and native
API configuration. Actual network and hardware results remain separate from unit
coverage. Public endpoint provisioning is an operator deployment task; local lab
success does not mean public DNS, certificates or firewall forwarding are installed.

### Verified secure-mode baseline (18 October 2026)

The isolated three-network run passed all eight call cases: UDP blocked at both
homes, at either home separately, or at neither home, with calls in both directions.
Each call checked decoded audio and video, SRTP, relay ICE, and clean hangup.
Endpoint trust checks and the native SIP client's rejection of an untrusted CA and
an incorrect certificate name also passed. The TURN framing regression passed all
3,804 fragmentation sizes on x86-64 and on the Raspberry Pi 4's ARM64 SDK; the
unpatched parser failed the expected negative control.

The default UDP mode also passed its ten network checks, including idle calls,
network impairment, blocked media, and recovery. Native video regression tests
passed. The Linux terminal unit suite passed 454 tests. The server's 43 JavaScript system
tests passed, including phone and desktop layouts. Terminal Linux system tests
passed 15 tests with one platform-inapplicable skip. Requirement validation found
no missing code anchors or HLR/LLR test-plan links. These results do not claim
100% execution coverage or public deployment qualification. Physical long-call
quality, institutional HTTP proxies, and public endpoint provisioning remain
separate deployment checks.

Android tests use `A-LLT-NNN` and `A-HLT-NNN` IDs and the same leading plan fields. `make test-android` runs JVM tests and Android lint; `make test-android-device` explicitly runs native/display checks on the device selected by `ANDROID_SERIAL`. Android requirements are Experimental while physical media and background-delivery qualification remain device-specific.
