# System-image and OS-upgrade implementation handoff

Original pause checkpoint: **5 November 2026**. The user subsequently requested
resumption. The sections below retain the original checkpoint evidence; the
continuation entry supersedes its pending-build and unsupported-combined statements.
This document is a handoff, not a claim of completion.

## Resumed work — 5 November 2026

Work resumed on `codex/combined-appliance-image`, using issue #167 for combined
role implementation and retaining this checkpoint for issue #168. Main remains
`42876ae6cf3cb8688a987365cdddfefd00769294` at the start of this continuation.
Release v0.3.90 is published, its tag resolves to that merge, and all eleven
expected assets were verified present and nonempty. The paused terminal raw-root
build completed: 807 exact installed selections, matching the current lock,
root SHA-256 `f56efe452bbadf75b9705b663220a7764b6a4d5d51ad4982c35ec9743a6c88ec`.

The combined profile, authenticated package closure and runtime storage/boot
contracts are now implemented. Its intent is the 52-package standalone union;
738 retained archives total 541,568,108 bytes. Shared archives are unchanged from
the standalone locks. Combined terminal UID/GID 1000 and server UID/GID 1001
have separate private application and operator paths, with root-private host
keys/certificates and one explicit combined host/boot identity. Cross-role
substitution is rejected. All role-taking build commands accept `combined`.

Direct component LLT/HLT coverage and CI now include combined identity, storage,
GPT startup gating and native environment transitions. Both private application
trees survive synthetic root replacement; real chroot UID checks reject cross
component data/operator/TLS access. These are synthetic namespace and emulation
checks, not physical boot or power-loss evidence. The detailed plan now covers
three image choices, joint admission/health, onboarding and performance qualification.

Updated standalone terminal component: 33,757,583 bytes, SHA-256
`01977611d72db495b3b1e6000190396658a33d78615985b5817f3dff355c233a`,
kernel `6.18.50+rpt-rpi-v8`. Its target ARM64 payload, import, unit-graph and
native environment-tool checks passed. The combined root/component build is
running in the new isolated WSL directory recorded by
`build_tools/tmp/current-combined-root.json`; require its final audit/READY.

Local verification: 240 runtime LLTs and 83 image-tool tests passed on Linux;
eight combined root-only HLTs passed. Windows completed 108 combined LLTs with
50 platform skips and 83 image-tool tests with 18 platform skips. Requirements:
313 source files, 303 anchored LLRs, 282 test plans, zero unmapped HLRs/LLRs.
This source checkpoint precedes final asynchronous build/Verify completion.
Final component identities, checks and merge status are recorded in
[PR #169](https://github.com/toastfr35/ZmalaCall/pull/169). Read that evidence and
the current private build-result catalogs before restarting a build.

No complete flashable application image or automatic system updater exists yet.
Offline application/service provisioning, matched loader/card assembly, secure
onboarding and joint update/health coordination remain the next implementation
work. Existing installer/user workflows are unchanged, so the user guides remain
accurate. No deployed host or SD card was modified.


## 1. Goal and current reality

Replace the normal SSH-based installation procedure with ready-to-flash SD-card
images for Raspberry Pi appliances. The approved installation choices are:

1. **Zmala Terminal**.
2. **Zmala Server**.
3. **Zmala Terminal + Server**, both components on the same Raspberry Pi. The user
   added this third choice immediately before this checkpoint.

These images must support automatic, signed whole-system updates, including
qualified Linux OS and distribution-package upgrades. Updates should happen as
soon as practical at safe idle, without requiring an administrator to schedule
them. Calls must win admission races. Power loss or a failed candidate must leave
a recoverable confirmed system. Terminal maintenance must display clear progress
in the selected language. Preserve identities, enrollment, host configuration,
supported application data and relevant TV restoration state.

**There is still no complete, flashable Zmala product image and no functioning
automatic whole-system update coordinator/feed.** There are implemented and
tested foundations, experimental runtime helpers, package roots, candidate
initramfs components and private boot experiments. Do not describe those as a
finished installer/updater or publish them as qualified system images.

The existing legacy installers and application-only updates continue to be the
supported installation/update path. This work has not replaced the running
server or terminal installations. Android updates are a separate existing
feature; Android version bumps in these PRs follow repository release rules.

## 2. Read these files first

- [AGENTS.md](AGENTS.md): issue/branch/PR, version, requirements, tests and trace rules.
- [update_upgrade.md](update_upgrade.md): detailed design, decisions, implementation
  history, staged checklist, recovery/qualification matrix and completion criteria.
- [build_tools/images/README.md](build_tools/images/README.md): implemented build
  commands, source audits, tool boundaries and important limitations.
- [docs/general.md](docs/general.md): requirement/test conventions, build/release
  conventions and experimental root integration commands.
- [docs/server.md](docs/server.md) and [docs/terminal.md](docs/terminal.md): current
  deployed behavior and the separately identified experimental host/image paths.
- `build_tools/images/{profiles.json,sources.lock.json,bootloader-profile.json}`
  and `build_tools/images/locks/`: actual checked-in build intent and locks.
- `zmala_system/`: the new shared experimental runtime implementation.

The latest combined-image request is recorded in
[issue #167](https://github.com/toastfr35/ZmalaCall/issues/167). Its implementation
has **not started**. The detailed master plan still needs to be updated throughout
for three installation choices; historical entries about two roles should remain
historically accurate.

This pause checkpoint has
[issue #168](https://github.com/toastfr35/ZmalaCall/issues/168).

## 3. Git, workspace and release checkpoint

Use the canonical checkout **`W:\git\zmala`**. Do not resume work in another old
checkout or mirror commits between branches.

- Verified merged main: **`42876ae6cf3cb8688a987365cdddfefd00769294`**.
- This is the squash merge of
  [PR #166](https://github.com/toastfr35/ZmalaCall/pull/166), implementing
  [issue #165](https://github.com/toastfr35/ZmalaCall/issues/165).
- PR #166's final head was
  `6f72c594c81376a547ff5da5e3b52ecac3963fe2`. Required **portable, windows and
  android Verify checks all passed on that head before merge**.
- Canonical local `main` was fast-forwarded to the merge above before this file
  was written. Current branch is **`codex/appliance-upgrade-handoff`**, created
  from that main commit for issue #168.
- This file is being saved as the pause checkpoint. No PR for it has been opened
  and no Android bump for a handoff PR has been made. Inspect `git status` on
  resumption; the document can remain uncommitted at this user-requested pause.
  Preserve it, then commit/publish it through the required workflow when resumed.
- Main's Android version is **0.3.90 / versionCode 99**. Every subsequent PR,
  including documentation-only PRs, must exceed then-current main. Normally the
  next handoff PR would use 0.3.91 / 100; recheck main rather than blindly using it.
- The merge triggered release **v0.3.90**. It was **not yet published at the last
  read-only check**. Do not announce it as ready without checking its actual tag,
  commit and assets. No agent monitoring is to continue during this pause.
- Previous release **v0.3.89**, at merge
  `080838b44f208f0747294ea71a691cbe3b2c03bf`, was fully verified earlier.

No tracked implementation edits remained at the branch switch. The existing
untracked **`.codex-attachments/` and `CAD/`** are unrelated and must be preserved.
Private `build_tools/tmp/` and ignored `hw_setup.md` must also be preserved.
Do not use `git add -A`, delete unrelated branches/worktrees, or discard private
TV-development work. This session did not audit all historical local branches.

The current release still has the nine user-facing downloads plus two existing
machine-consumed legacy terminal update assets:

```text
ZmalaTerminal-Installation.pdf
ZmalaTerminal-Guide.pdf
ZmalaTerminal-Pi4-setup.exe
ZmalaServer-Installation.pdf
ZmalaServer-Guide.pdf
ZmalaServer-Pi4-setup.exe
ZmalaPhone-Installation.pdf
ZmalaPhone-Guide.pdf
ZmalaPhone.apk
ZmalaTerminal-Update.json
ZmalaTerminal-Update.tar.gz
```

Verify all eleven are nonempty and the release tag resolves to the expected
merge before announcing this release. Do not remove the last two files to force
a nine-asset count: deployed legacy updaters consume them. There are no new SD
image assets in this release. The eventual image publication set needs an
explicit migration of the workflow/allowlist and guides.

## 4. Decisions already made

- Raspberry Pi 4, ARM64, Raspberry Pi OS/Debian **Trixie** is the experimental
  starting platform. A 32 GB card is the target; actual minimum capacity and
  free-space headroom still need complete-image measurement.
- Build replacement system images and use **RAUC** for inactive-slot installation.
  Do not run uncontrolled live `apt upgrade` as the product update mechanism.
- Keep the legacy application-only updater separate. `PROD016` describes the
  legacy application-maintenance area; **`PROD017`** introduces image-managed
  system maintenance. Earlier decisions excluding OS upgrades applied to the
  legacy feature, not this new project.
- Use two matched boot/root slot groups and one deliberately managed persistent
  data area. Do not carry an uncontrolled persistent `/etc` overlay or old package
  database into a new OS generation.
- Native Pi `tryboot` was investigated first. The audited reference backend's FAT
  `autoboot.txt` replacement and early mark-good service were not accepted as a
  qualified durable selector/health policy.
- The current alternative is pinned **U-Boot**, redundant raw environment state,
  an explicit confirmed/trial model and bounded early-watchdog handover. It is
  still experimental and not yet integrated into complete product images.
- Common loader/firmware and EEPROM updates are not silently included in ordinary
  A/B root replacement. Never run an EEPROM recovery/update image as this probe.
- A/B rollback does not automatically roll back shared application data. Supported
  data generations, checkpoints/migrations and incompatible-transition refusal
  are still required.
- Preserve the existing server and terminal original cards/installations. The user
  has a spare SD card, **not a spare Pi**. Physical tests need arranged card swaps
  on term2; do not assume standing permission to overwrite or replace live media.

## 5. Implemented build/deployment tooling

All of this tooling is experimental and deliberately outside the normative
runtime requirement baseline. Its regression tests are under `tests/adhoc/`.

### Sources and package inputs

`sources.py` validates pinned source archive hashes and bounds safe extraction.
The exact commits are in `sources.lock.json`:

- `rpi-image-gen`: `ff5fb451fac47debf441a5a2b39aa3ade7988bd6`.
- Native Pi RAUC backend audit:
  `c8aa8ab78f9eb12c42d5b45f7d27c430bce8b7ef`.
- U-Boot v2026.10: `5508406582f6f7120dce0c4b3059819a41788db2`.

`package_lock.py` performs authenticated download-only APT intake without changing
host package state. It retains archive identities/hashes, signed repository
metadata and public archive keyrings. `local_repo.py` builds a private offline
file repository from externally anchored retained caches, rejecting conflicting
versions/contents. This unsigned local repository is a build input, not a public
device update source.

There are two different kinds of checked-in input:

- `base-intent.json` is the **observed exact clean pre-boot base inventory**;
  `base.json` locks its 259 archives. Do not edit that inventory to pretend new
  boot/application tools were originally present.
- Role intents and dependency closures are separately reviewed. Current role
  locks contain **173 server archives and 723 terminal archives**. Both now
  include ARM64 `libubootenv-tool` and dependencies. Fresh terminal intake also
  selected newer Mesa userspace and Linux development headers. These changes
  are unqualified build inputs, not deployed package upgrades. The actual
  pinned boot kernel remains `6.18.50+rpt-rpi-v8` in these roots.

**Input-retention limitation:** the repo contains locks, hashes and tooling, not
all Debian/Raspberry Pi binary archives or their retained metadata. Existing
verified caches are available on this PC, described below. Durable distribution
of retained build/source inputs and the complete build-toolchain closure is not
finished. A fresh current-APT intake can change versions and lock hashes; it must
be reviewed, not silently substituted. Exact old artifacts cannot be claimed
reproducible from the Git repo alone if their retained inputs are unavailable.

### Root and component builders

- `root_build.py` builds an audited OS-package root tar using the reviewed base
  plus role locks, `mmdebstrap`, QEMU and isolated unprivileged Linux namespaces.
  It checks installed package identities and host package-state preservation.
  It does **not** install the Zmala applications or assemble a bootable card.
- `root_cleanup.py` removes generated identities/secrets from disposable roots
  and applies the diagnostic EEPROM-updater safeguard. Do not run it on `/` or
  an installed Pi. Whole legacy installation scripts are not safe first-boot hooks.
- `image_state.py` prepares a new offline root tar: slot-local package database,
  bounded variable seed, experimental runtime modules/policies, PID1 gate,
  executable boot backend and volatile journaling policy. Source roots remain
  unchanged. The result still has no complete boot/application provisioning.
- `factory_data.py` emits an empty, root-private, marked data tar. It generates
  no shared device identity and formats/mounts nothing.
- `initramfs_build.py` / `initramfs_worker.py` build and audit a candidate initramfs
  with the target's own tools in separate user/mount/network/PID namespaces.
  Target ARM64 imports, executable entry, actual vendor-unit graph and native
  environment-tool read/write operations are checked. Incomplete builds have no
  accepted `READY.json`; retain failed output for diagnosis.
- `inspect_disk.py` shares the bounded GPT parser with runtime admission but only
  opens regular image files. `inspect_boot.py` checks FAT geometry. Passing these
  checks is not proof of firmware contents or bootability.
- `bootloader.py` emits/audits pinned diagnostic Kconfig/profile input. Its
  watchdog takeover sample is a **probe**, not the product trial-health policy.

Important build fixes already made: hook files emitted with LF; anchored tar
exclusion omits root `/dev` without deleting kernel directories also named `dev`;
Python extension ELF dependencies are copied before the complete stdlib because
`copy_exec` skips existing destinations; copied private executable modes are
normalized. Do not undo these fixes when simplifying the builder.

## 6. Implemented experimental runtime

The runtime is shared by the experimental Pi server and terminal. Existing
deployed hosts do not invoke these new image boot paths.

### Immutable root and selected persistence

`host_layout.py` / `host_storage.py` define and validate fixed policies:

- Slot-local package database: `/usr/lib/zmala/slot-dpkg`.
- Immutable initial `/var` seed: `/usr/lib/zmala/var-seed`.
- Fresh bounded RAM `/etc` overlay and `/var`/`/tmp` each boot.
- Only explicit persistent bindings: machine identity, hostname, NetworkManager
  profiles/state, Bluetooth pairing, SSH key directory, operator configuration,
  role application state, and server certificate state.
- Fixed owners/modes, bounded records/seed, link refusal, no input-device selection
  or formatting. Standalone role application UID/GID is currently 1000.
- Experimental journal budget is 32 MiB; legacy installation remains 64 MiB.

The helper validates already mounted input roots/data and prepares owned views.
Failure cleanup preserves input mounts, committed identity and the original
failure; it retains data if dependent owned views could not be removed.

### First identity

`device_identity.py` accepts an explicitly marked compatible factory data mount,
uses a persistent nonblocking root-private lock inode, obtains kernel entropy,
and commits identity through staged files, synchronization and atomic rename
before publishing initialized data state. Retrying preserves a committed
identity. It refuses corrupt initialized state rather than inventing a new one.

It does not select/format/expand disks, create SSH keys, import legacy state,
claim the server or enroll the terminal.

### Early boot and PID1 gate

- `boot_layout.py` requires exact role/layout policy and one kernel slot/root
  PARTUUID pair. Experimental partition numbers are boot selector 1, boot A/B
  2/3, root A/B 4/5 and persistent data 6.
- `boot_devices.py` binds the mounted root's major/minor to actual kernel topology,
  block node, GPT entry and ext4 identity/geometry. Data must be the unique
  declared sibling under the same parent; there is no global label lookup.
- `boot_storage.py` mounts only admitted data, initializes identity, prepares
  views, writes the selected read-only root `fstab` entry in RAM, then publishes
  complete private current-boot readiness.
- `boot_entry.py` runs in initramfs **`local-bottom`**, before Debian's
  `init-bottom` udev hook moves `/dev` away. Failure remains fenced.
- `boot_gate.py`, `zmala-host-storage.service` and the `sysinit.target` drop-in
  independently require complete current-boot records, mounted bindings and
  committed identity before normal startup. A killed/missing early helper cannot
  simply be treated as successful preparation.
- PR #166 corrected a real path-admission defect: the default PID1 root `/` had
  been rejected by a helper previously tested with temporary root directories.
  A direct regression now reaches policy validation using the actual default path.

The startup gate's actual systemd unit graph has been checked offline. That is
not evidence of a complete actual PID1/image boot.

### Confirmed/trial control

`boot_state.py` defines a bounded, exact unique-key record: schema, role,
confirmed slot, distinct optional trial, one remaining attempt, eligibility,
transaction identity and bounded generation. The confirmed slot remains eligible.

`boot_select.sh` clears transient outputs and selects an eligible confirmed slot
or trial. It persists trial consumption **before** selecting that trial. Save
failure chooses the confirmed slot. A subsequent boot with no attempt remaining
falls back without another write. The future loader must refuse empty selection.
Compiled fallback environments must contain **none** of the `zm_*` contract fields;
corrupt state must never turn into an implicit factory default.

`boot_environment.py` admits native access only after marked current-boot
readiness, Pi 4 SD topology, selected root/data identities, both GPT copies and
fixed disjoint raw ranges are checked. The current experiment uses **two 64 KiB
environment copies at 1 MiB and 5 MiB**, with the first partition starting at or
after **8 MiB**. Raw access uses fixed paths/keys, bounded tools, root-private
generated configuration, empty fallback defaults, nonblocking lock/CAS and exact
readback. No CLI accepts arbitrary device paths or offsets. This production
admission path has not yet been exercised against the actual Pi by this code.

The installed adapter is `/usr/lib/zmala/bin/boot-backend`; source is
`boot_backend.py`. It exposes:

```text
get-current
get-primary
get-state A|B
set-state A|B good|bad
snapshot
stage A|B TRANSACTION
confirm TRANSACTION GENERATION
cancel TRANSACTION
```

`set-primary` deliberately fails because it cannot identify a product transaction.
The eventual RAUC configuration must use `activate-installed=false`; the
coordinator must call explicit `stage` only after complete inactive boot/root
installation, durable transaction recording and safe admission. Generic mark-good
changes eligibility and **does not confirm health**. Confirmation requires the
currently booted consumed trial and matching transaction/generation. The backend
does not evaluate candidate contents or product health.

### Watchdog integration remains unfinished

An early PID1 runtime watchdog can keep petting an unhealthy trial forever.
`trial-watchdog.conf` therefore packages `RuntimeWatchdogSec=0` during trial
startup. The complete image must qualify a loader-armed watchdog, bounded kernel
handoff (`watchdog.handle_boot_enabled=1` plus a **nonzero** `watchdog.open_timeout`),
and a later qualified product-health transfer before PID1 takes ownership.
systemd 257 has a writable `RuntimeWatchdogUSec` manager property for that transfer;
the current backend does not invoke it. Do not ship the incomplete handover as a
working product watchdog scheme. The 60-second diagnostic probe setting is not
automatically an appropriate final deadline for all three product images.

## 7. Requirements and evidence

All new runtime requirements are explicitly **Experimental**. Installer/build
checks stay outside the runtime baseline. The implemented requirement families:

| Boundary | Server | Terminal |
| --- | --- | --- |
| Host storage | HLR-SRV-HOST-008; LLR 009–012 | HLR-TERM-MAINT-035; LLR 036–039 |
| First identity | HLR-SRV-HOST-013; LLR 014–016 | HLR-TERM-MAINT-040; LLR 041–043 |
| Early storage boot | HLR-SRV-HOST-017; LLR 018–021 | HLR-TERM-MAINT-044; LLR 045–048 |
| Confirmed/trial helper | HLR-SRV-HOST-022; LLR 023–027 | HLR-TERM-MAINT-049; LLR 050–054 |

Latest requirements run: **313 mapped source files, 301 anchored LLRs, 278 test
plans, zero unmapped HLRs/LLRs**. Baseline counts were PROD 17; server HLR 40 / LLR
133; terminal HLR 47 / LLR 159; Android HLR 7 / LLR 9. Owning comments and
reciprocal links were synchronized. Generated `requirements/output/` stays ignored.

Latest focused verification:

- Linux: **78 state/storage runtime LLTs passed**.
- Linux root: **all eight** isolated host-storage, first-identity, GPT boot and
  native boot-state HLTs passed, covering both standalone roles.
- Offline image-tool group: **82 passed on Linux**; Windows completed 82 with
  **18 explicit platform skips**. Windows runtime state/storage tests completed
  78 with **30 explicit platform skips**. Skips are not successful execution.
- Required full portable/windows/android Verify jobs passed on PR #166's final head.
- The pinned U-Boot hush interpreter passed **24 decision cases**, with `saveenv`
  explicitly substituted. Real Linux environment-tool HLTs separately exercised
  persistence on new regular GPT files. These two tests do not jointly establish
  U-Boot persistence on a physical SD card.
- Actual native-tool HLTs checked trial consumption, fallback, confirmation in both
  directions, cancellation, stale-state refusal, one/two bad environment copies,
  no imported defaults and unchanged bytes outside the reserved environment ranges.
- First-identity HLTs kill real initializer processes at eight synchronization
  boundaries per role and retry on new ext4 fixtures. Process death leaves the
  kernel running and is not a physical power cut.

New server component evidence after PR #166:

- Audited raw OS root: **314 exact installed selections**.
- Prepared root SHA-256:
  `c22a15611565699a3e78ad2747e50bdc5737585c7bec40b0bb9fd4b19822e1c1`.
- Candidate initramfs: **29,313,945 bytes**, SHA-256
  `e83e112762da521ef6321e53e84513d117881a69632f82d1fdaf4d2d0c24fe52`.
- Kernel `6.18.50+rpt-rpi-v8`; **15** exact copied runtime/role files; target
  imports/prereqs, vendor-unit graph and actual ARM64 environment-tool read/write
  all passed. Complete image / hardware boot / production qualification flags are
  deliberately false.

The terminal's earlier PR #164 candidate initramfs was 33,750,541 bytes with ten
runtime/role files. **Do not mistake that older artifact or READY marker for a
new terminal build containing PR #166's role lock and boot-control modules.**

### Earlier physical experiments: useful but limited

Private minimal U-Boot lab images, not complete Zmala images, exercised A/B
selection/fallback, manual counter changes, healthy watchdog handoff, a controlled
pre-root stall, one newer-copy CRC fault and an operator power cut during repeated
environment commits. Those experiments used earlier lab scripts/counters, not the
new complete confirmed/trial product path. Original term2 storage was restored.

Lessons already established:

- A forced undersized FAT32 selector volume was invalid; FAT geometry checks and
  the corrected FAT16 lab selector matter.
- Missing explicit lab slot arguments caused early boot failure; do not guess a slot.
- Default U-Boot FDT/initrd relocation fragmented graphics CMA and caused missing
  HDMI despite a running kernel. Bounded relocation ceilings restored graphics in
  that experiment. Do not blindly copy one address into every future image.
- A new OS slot needs matched kernel/initramfs/DTB/overlays plus qualified firmware
  fixups and memory placement. Reusing an old common DTB across major kernels is
  not a qualified matched-payload design.
- EEPROM updater safeguards must be applied before diagnostic first boot.

Physical power-loss, reboot, early-watchdog and actual-media behavior require a
complete attributable matrix. None of the above closes that matrix.

## 8. Current background work and private local state

At this checkpoint, the already-started **terminal OS-package root rebuild was
still running** under WSL/QEMU. It is permitted to finish its existing isolated
job; no follow-on initramfs build or live deployment has been queued. There is no
agent monitoring after this pause. The GitHub v0.3.90 release job may also finish
independently. Recheck both on resumption; do not start duplicate jobs blindly.

The Windows exec session for the package-root job was 79930, but session IDs are
ephemeral and not a recovery mechanism. Use result files/logs and actual processes.
The job was configuring the target kernel/initramfs during the last observation,
not operating a real SD card. Root builders have a one-hour process timeout.

Existing ignored metadata under `build_tools/tmp/`:

| File | Meaning / caution |
| --- | --- |
| `boot-tool-root-build.log` | Overall new server/terminal package-root job; server completion already recorded |
| `current-boot-tool-root-build.json` | Current terminal disposable output directory; its `build.log` has target progress |
| `isolated-locked-root-build.json` | New successful server raw-root result |
| `public-locked-terminal-root.json` | Replaced only when the terminal raw-root job succeeds; otherwise still the older 805-package result |
| `server-package-intake-result.json`, `terminal-package-intake-result.json`, `base-package-intake-result.json` | Retained cache locations and anchored lock hashes |
| `prepared-host-roots.json` | Mixed checkpoint catalog: new server prepared root, potentially older terminal prepared root |
| `server-initramfs-build.json` | New successful server component result described above |
| `terminal-initramfs-build.json` | May still be the older PR #164 result; check source/root/lock/payload identity |
| `boot-state-merge-evidence.json` | Exact #166 head, merge, version and required-check results |
| `boot-state-hush-evidence.json` | 24 pinned-interpreter cases, exact script/binary/config hashes and stated substitutions |
| `boot-state-requirements.log` | Last tracked-input requirements build |
| `boot-state-all-runtime-hlt.log`, `boot-state-image-tests.log`, `boot-state-image-tests-windows.log` | Focused integration/build-tool results |
| `combined-image-plan-addition.md` | Optional detailed draft for issue #167; substantive intent is also recorded below |

The retained caches and built artifacts are generally under
`$HOME/.local/share/zmala-image-lab/` **inside WSL**, outside the checkout. The
metadata above records precise locations. Preserve accepted and failed artifacts
until their identities/results have been recorded. A file named `root.tar` or
`initramfs.pending.img` alone is not an accepted build.

Private helper scripts in this folder use existing authenticated access and may
refer to private paths. They are conveniences, **not required public tooling and
not files to commit**. Public continuation must use the actual `build_tools.images`
commands and checked-in code, or deliberately replace the helper with reviewed
public tooling. Never print authentication material from helpers.

Hardware connection details/passwords are in ignored local `hw_setup.md`, not this
public handoff. No live hardware operation was performed in this boot-state work.
Term2 was last known restored to its original card; the server stayed on its
original installation. Their live health and the spare card's current location
were not freshly checked. Do not assume a drive letter identifies the same card.

## 9. Reproduce/check the implemented boundaries

Windows checkout: `W:\git\zmala`, PowerShell. Existing development venv:
`.venv\Scripts\python.exe`. Linux environment: **WSL `Ubuntu-24.04`**, checkout
normally `/mnt/w/git/zmala`, Python 3.12.3 on the build host. Target Python is 3.13.
Use the exact WSL distribution name; `Ubuntu` is not installed under that name.

Use Linux for symlinks, namespace tests, package acquisition and ARM64 builds.
Build roots as an **ordinary Linux user**, with working subordinate UID/GID maps,
`mmdebstrap`, `unshare`, offline APT tools and registered QEMU ARM64 binfmt support.
Do not run root builders as host root. Root HLTs use sudo only for new isolated
fixture files/namespaces, not for installed Pi devices.

Windows MSYS make is available at `C:\msys64\usr\bin\make.exe`. Normal commands
below assume the appropriate requirements/dev dependencies are installed; see
the CI dependency step and image README. Keep at least 32 GiB free on **both**
the output filesystem and `/tmp`. New output paths are required. Full emulated
package-root builds take many minutes; reuse an unchanged audited root rather
than rebuilding it for every runtime-source change.

From a clean checkout:

```sh
python3 -m build_tools.images check
python3 -m unittest discover -s tests/adhoc -t . -p 'test_image*.py' -q

python3 -m unittest \
  tests.server.LLT.test_appliance_storage tests.terminal.LLT.test_appliance_storage \
  tests.server.LLT.test_device_identity tests.terminal.LLT.test_device_identity \
  tests.server.LLT.test_boot_storage tests.terminal.LLT.test_boot_storage \
  tests.server.LLT.test_boot_state tests.terminal.LLT.test_boot_state -v

sudo python3 -m unittest \
  tests.server.HLT.test_appliance_storage_linux tests.terminal.HLT.test_appliance_storage_linux \
  tests.server.HLT.test_device_identity_linux tests.terminal.HLT.test_device_identity_linux \
  tests.server.HLT.test_boot_storage_linux tests.terminal.HLT.test_boot_storage_linux \
  tests.server.HLT.test_boot_state_linux tests.terminal.HLT.test_boot_state_linux -v

make requirements
```

Root HLTs require `fdisk`/`sfdisk`, `util-linux`, `e2fsprogs`, loop support and
`libubootenv-tool`. CI explicitly installs and runs them; a skip must not substitute
for that integration run. Current CI also runs full component tests, native media
regressions, lint, Android build/lint/tests and independent ad-hoc installer tests.

Build commands, using retained cache directories whose lock hashes match the
checked-in index (substitute actual new absolute output paths):

```sh
python3 -m build_tools.images build-root server \
  --base-cache /path/to/base-cache --role-cache /path/to/server-cache \
  --output /path/to/new/server-root

python3 -m build_tools.images prepare-root server \
  --source /path/to/server-root/root.tar --expected-root-sha256 ROOT_SHA256 \
  --base-cache /path/to/base-cache --role-cache /path/to/server-cache \
  --output /path/to/new/server-prepared

python3 -m build_tools.images build-initramfs server \
  --source /path/to/server-prepared/root.tar --expected-root-sha256 PREPARED_SHA256 \
  --base-cache /path/to/base-cache --role-cache /path/to/server-cache \
  --output /path/to/new/server-initramfs

python3 -m build_tools.images factory-data server --output /path/to/new/server-data
```

Use `terminal` with its own matching inputs for the other implemented role.
**`combined` is not yet a supported command/profile role.** These commands do
not assemble or flash a complete SD image. Consult `--help` and the image README
for authenticated `lock-base`, `lock-packages`, source fetching, public keyrings
and inspecting retained inputs. Never replace a failed authenticity/hash check
with an unauthenticated download or invented successful record.

For the current workspace, a private tracked-input export helper was used for
`make requirements` to avoid unrelated ignored/private Floorplan material in the
inventory. A clean clone should use normal `make requirements`. If using an
export, include current contents of newly staged files; a plain archive of HEAD
omits uncommitted edits. Do not commit generated `requirements/output/`.

## 10. Combined-image implementation still required

Issue #167 is approved scope, not implemented functionality. Use an explicit
`combined` image/manifest role, displayed as **Zmala Terminal + Server**, and keep
both standalone images. Use one OS, not nested installations/VMs/containers.

Concrete design direction to implement and verify:

- Resolve the authenticated union of both role package intents against the same
  reviewed base. Keep common/role locks synchronized and retain the combined
  archives independently. Do not alter the observed base inventory as a shortcut.
- Extend fixed role validation in profiles, runtime policy, factory identity,
  boot state/selector, CLI/build tools and compatibility metadata. Reuse a central
  role definition where appropriate rather than scattering inconsistent checks.
- Keep one host identity, NetworkManager/Bluetooth configuration, A/B slot and
  maintenance transaction. Role conversion from standalone is not an implicit
  update; it needs an explicitly supported migration.
- Separate terminal and server process/data identities. The proposed experimental
  mapping is terminal UID/GID 1000 and server UID/GID 1001 on combined, with each
  standalone role retaining 1000. Persist both application trees separately at
  private ownership/mode; split operator configuration by component. Do not share
  administrator credentials, database, TLS private material or terminal enrollment
  through a common application-readable directory. Narrow credential/broker access
  should replace broad permission changes.
- Support both server first-owner setup and normal terminal enrollment without
  SSH. Configure host networking once. Preserve LAN-only server administration.
  Test local terminal-to-local-server secure registration with the correct TLS
  authority **without assuming router NAT loopback**. Check listener/user-name
  collisions and distinguish tunnel-listener accounts from developer shell users.
- One coordinator owns RAUC/reboot. Both components must grant safe admission:
  terminal calls/ringing/photo/setup/TV-sensitive work and server SIP dialogs,
  global TURN relay traffic, database/backup/claim/credential operations. A busy
  component prevents activation; one service cannot independently reboot the host.
- Health confirmation must cover both local components. Valid unclaimed-server
  and terminal-setup waiting states must not require the user to finish onboarding
  before the host can become healthy. Separate external network failures from
  local faults. TV standby or terminal UI restart must not stop the server.
- Preserve both application data generations and TV restoration state across
  one update/reboot/rollback. Health checks must not wake camera or television.
- Measure actual combined 32 GB fit, RAM/CPU/thermal behavior and calls while
  server relay traffic is active. Extend requirements, direct tests, guides,
  SD preparation UI and publication choices accordingly.

Do not relocate the current live server onto term2 merely because the combined
image was requested. That would be a separate controlled migration/test action.

## 11. What is left overall

The detailed checklist is in sections 16–17 of `update_upgrade.md`. This is the
practical remaining implementation map:

### Complete image assembly and provisioning — highest next priority

1. Finish/record the new standalone terminal root/component checks, then add the
   combined profile and its tests without losing existing standalone behavior.
2. Assemble the complete partitioned SD artifact: common loader/selector, both
   matched boot/root slots and explicitly marked factory data. Verify GPT/FAT,
   bounds, content identities, loader/environment initialization and actual fit.
3. Package a reviewed U-Boot build and actual payload-loading script around the
   new selector. Seed both redundant environment copies with required loader
   defaults plus explicit factory state; invalid CRC state must not factory-reset.
4. Load the slot-matched kernel/initramfs/DTB/overlays with qualified firmware
   fixups and graphics memory placement. Establish recovery behavior for missing
   or invalid payloads. Qualify common-loader compatibility across OS generations.
5. Install the real terminal Python/native media workers, server app/admin assets,
   locked application dependencies, system users, units and host configuration
   into the images offline. Reuse declarative parts of legacy installers; **do not
   run the whole live installer in a chroot or at first boot**. Retain matching
   native/TURN/media corrections and ABI checks.
6. Complete filesystem/host policy for actual service writes, native device access,
   SSH host-key generation, safe optional data expansion and setup/recovery. Disable
   competing package/app update mechanisms on image-managed systems while keeping
   legacy support. Avoid introducing a shared factory password or key.
7. Implement secure server first-owner claiming, terminal network/QR enrollment,
   combined onboarding and resumable first boot without SSH.
8. Boot the complete artifact on the spare card with the original card retained,
   using an arranged hardware window. Do not call a minimal lab boot this result.

### Signed A/B update coordinator and health

- Signed metadata/feed roles, trust provisioning/rotation, authenticated bundles,
  compatibility/freshness/withdrawal checks, bounded downloads/cache/history.
- One durable reconciled transaction state machine around complete inactive
  boot/root installation, data preparation, activation, trial and confirmation.
- Inactive-only device selection/write guards and exact content verification.
- Bounded kernel-to-userspace watchdog handover and local product health for each
  installation choice, including degraded external connectivity and valid setup
  waiting states. Generic RAUC mark-good is insufficient.
- Deterministic recovery/quarantine/repair for each interrupted state, including
  installation, environment commit, data checkpoint/migration and confirmation.

### Product integration

- Terminal safe-idle leases, admission race recheck, localized visible progress,
  restart/recovery and durable TV restoration. Preserve active calls and viewing.
- Server maintenance admission covering **global** SIP and TURN activity, protected
  persistence work, status/reconnect behavior and self-maintenance.
- Combined admission and health across both services; one reboot/transaction.
- Backward-compatible data/migration generations, terminal/server imports and
  retained-original-card recovery. RAUC does not solve shared-data rollback.

### Qualification and distribution

- Real A→B→A boot/update sequences, physical power cuts and hangs at the actual
  selector/early-boot/health/data boundaries on supported hardware.
- At least one real different-major-OS candidate, including native/media ABI,
  device tree, host/network/Bluetooth/TLS configuration and data compatibility.
- Calls, long idle/offline behavior, CPU/RAM/thermal/storage margins and no
  unintended TV/camera wakes, for all applicable image choices.
- Retained complete build/toolchain/source inputs, notices/provenance and a
  qualified publication process. No production signing credential in the repo.
- User-friendly SD preparation/download path, all three image choices, regenerated
  Word/PDF guides and fresh installation using only public downloads/instructions.
- Controlled beta migration, soak/promotion and monitoring. Retire normal SSH
  installer links only after replacement installation/recovery is qualified.

## 12. How to resume efficiently

The user was concerned about slow progress. The previous approach became too
incremental: many foundations were validated/merged before an end-to-end image
existed. Do not spend the next session producing more small framework-only PRs.
Keep safety gates, but organize the next cohesive milestone around **a complete
image that boots and runs Zmala end to end**, then finish full update qualification.

On an explicit resume:

1. Read this file, `AGENTS.md`, the master plan and actual `git status`; preserve
   the checkpoint/private/unrelated files. Check issue #168's document state and
   use an Android version bump before opening its PR if it is published separately.
2. Inspect the existing terminal build metadata/log before starting another build.
   Accept it only after its final audit/READY and matching new role lock. If it
   failed, preserve diagnostics and repair the actual cause. Do not accept an
   older successful terminal artifact from a different source/lock.
3. Check the already-triggered v0.3.90 release if still relevant. Verify exact merge
   and eleven assets; stop monitoring after success. Do not create a recurring
   automation to watch this specific job.
4. Work on issue #167 on an appropriate new `codex/` feature branch from current
   main. Update the detailed plan for the third installation choice. Identify
   affected runtime requirements, owning anchors, tests and guides before edits.
5. Finish combined foundations as part of the complete-image vertical slice, and
   move into offline product provisioning/loader/card assembly. Reuse accepted
   unchanged package roots; runtime-source changes normally need preparation and
   component rebuilds, not full emulated package installation again.
6. Keep precise evidence: source commit, locks, root/initramfs/image hashes,
   environment and actual check scope. A hardware plan is not a passed run.
7. Arrange physical card writes/swaps only when a complete candidate needs them.
   Freshly verify card identity/capacity and required Windows administrative access;
   do not infer permission from an old drive letter or old diagnostic-card approval.

Use issue → feature branch → PR → successful required Verify → GitHub merge.
Never push directly to main or bypass failed checks. Keep code, technical/user
documentation, Doorstop links and tests synchronized. `--next-id` is required
before allocating runtime requirement IDs; source comments remain standalone
`@llr` anchors. Every LLR/HLR needs direct LLT/HLT plans/assertions with the five
stable test-header fields. Keep installers/tool checks under `tests/adhoc/`, and
run them independently. Run `make requirements` after requirement/trace/plan edits.

No further implementation, build launches, release monitoring, live Pi operations,
TV/camera activity or card writes are requested during this pause.
