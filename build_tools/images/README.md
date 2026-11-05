# Appliance image development tools

Implementation issue [#140](https://github.com/toastfr35/ZmalaCall/issues/140).
See [the staged system-update plan](../../update_upgrade.md). These tools are
build/deployment tooling, not an installed updater. **There is no production SD
installer or automatic system-update feed yet.**

## Current commands

Run from the repository root:

```sh
python3 -m build_tools.images check
python3 -m build_tools.images probe-config terminal --output build_tools/tmp/terminal-probe
python3 -m build_tools.images probe-config server --output build_tools/tmp/server-probe
python3 -m build_tools.images fetch imagegen --cache build_tools/tmp/image-sources
python3 -m build_tools.images fetch backend_audit --cache build_tools/tmp/image-sources
python3 -m build_tools.images fetch bootloader_audit --cache /path/to/new/outside-checkout-cache
python3 -m build_tools.images bootloader-config --output /path/to/new/bootloader-profile
python3 -m build_tools.images inspect-bootloader /path/to/resolved-build/.config
python3 -m build_tools.images inspect-root /path/to/offline/root
python3 -m build_tools.images inspect-disk /path/to/uncompressed-probe.img
python3 -m build_tools.images inspect-bootfs /path/to/uncompressed-probe.img
python3 -m unittest tests.adhoc.test_image_foundation -v
python3 -m unittest tests.adhoc.test_image_disk -v
python3 -m unittest tests.adhoc.test_image_boot -v
python3 -m unittest tests.adhoc.test_image_bootloader -v
python3 -m unittest tests.adhoc.test_image_eeprom -v
```

Use Linux for source extraction/building. Windows can validate profiles and emit
configurations, but source trees contain Unix symlinks and may fail extraction
without additional privileges. WSL Ubuntu 24.04 is available for development;
native ARM64 remains the preferred eventual image builder. `python3-debian` and
`python3-yaml` are needed for the upstream metadata/configuration command. Full
image generation needs upstream's other build dependencies too.

`sources.lock.json` fixes upstream commit IDs and archive SHA-256 hashes. Fetch
checks the digest before extraction, bounds archive expansion, rejects traversal,
hard links, device nodes and escaping links, and checks the extracted source tree.
It never executes a downloaded script. Destinations must be new; an interrupted
extraction is deliberately not reused. Use a new cache or remove only the known
incomplete extraction directory before retrying. Source-cache changes are not
silently accepted as a new upstream version.

The separately pinned `bootloader_audit` source is U-Boot `v2026.10` at the exact
commit/digest in `sources.lock.json`. Its reviewed archive contains 41,465 members
and 264,670,480 expanded file bytes. Only that source receives larger budgets:
64 MiB compressed, 384 MiB expanded and 50,000 members. The other two sources keep
their 32 MiB / 160 MiB / 10,000-member limits. Individual files remain capped at
32 MiB, and the same path, link, hash and tree-verification rules apply. Cached
archives must be regular files; FIFOs/devices/links are rejected before reading.

`profiles.json` records the common base and role package **intent**, not a complete
resolved package lock. The terminal intent reuses the existing dependency list;
server npm/build dependencies and full secure-relay provisioning remain to be
separated into build/runtime sets. The selected RAUC package is Debian Trixie's
`1.13-3+deb13u1`; its role dependency closures are now retained and reviewed.
Complete builder/toolchain inputs and use of the locks in factory builds still
need to be established before production builds.

The emitted `probe.yaml` is a minimal Pi 4 A/B **boot experiment**. It does not
install Zmala, a bootloader backend, production keys or an update coordinator.
`package-intent.txt` is separate from the minimal probe package list. Its adjacent
`status.json` explicitly records missing package locking, product provisioning,
boot safety and hardware qualification. Nothing here publishes or promotes it.
Probe artifact versions are explicitly `unqualified-<role>-probe1`; they do not
inherit a misleading release version from the parent checkout's Git tags. This
lab label is not a reproducible package/build identity for production.

After fetching, the upstream configuration resolver can check each probe:

```sh
# Replace <commit> with the imagegen commit in sources.lock.json.
build_tools/tmp/image-sources/imagegen-<commit>/rpi-image-gen config \
  build_tools/tmp/terminal-probe/probe.yaml \
  --write-to build_tools/tmp/terminal-probe/resolved.env
```

Build with the emitted project as the explicit source directory, so imagegen
discovers its executable customization hook:

```sh
build_tools/tmp/image-sources/imagegen-<commit>/rpi-image-gen build \
  -S build_tools/tmp/terminal-probe \
  -c build_tools/tmp/terminal-probe/probe.yaml -B /path/to/new/lab-build
```

The project's `layer/zmala-probe-eeprom.d/hooks/customize99-zmala-eeprom-scope`
is a standalone copy of
`eeprom_policy.py`, emitted with Unix line endings. It masks the known
`rpi-eeprom-update.service` in the offline root, before A/B assembly, without
executing systemctl, chroot or firmware utilities. **Do not omit `-S`.** The
configuration requires this project-local layer, so a missing source directory
fails layer resolution instead of silently assembling an unmasked image. The
unqualified upstream probe otherwise inherits the stock EEPROM updater, which
is outside this work's scope. The hook refuses the host filesystem root, linked
policy parents and existing operator overrides; rerunning an existing correct
mask is harmless. Inspect the resulting root before writing any card.

Masking this known OS service is not a full firmware safety audit: inspect the
actual boot payloads too, and never substitute a recovery/EEPROM image for this
probe. It neither upgrades EEPROM nor establishes that an old EEPROM supports
the intended boot path. Existing installed devices are not changed by this tool.

The upstream `image-rota` probe layer uses its own selector partition size and
persistent `/var` policy. Those are acceptable subjects of a boot experiment,
not adopted production storage policy. In particular, its per-slot persistent
package database cannot be reused unchanged across replacement root images.
The custom narrow persistent mounts and qualified selector are still required.

`inspect-bootfs` first validates both GPT copies and the probe layout, then reads
the FAT BIOS Parameter Block in each of the three boot volumes. It rejects
inconsistent geometry, a filesystem larger than its partition, invalid root
directory geometry and FAT tables too small for their data clusters. In particular,
a forced FAT32 volume with fewer than 65,525 data clusters is rejected, even when
its signature and GPT are valid. The private 32 MiB common-loader experiment
exposed that case; use a valid FAT16 footprint there or qualify a larger FAT32
volume. Do not infer the actual FAT type from a volume label or formatting flag.
The command reads regular image files only; it does not flash, mount or repair
anything. Geometry validation does not check file chains, payload signatures,
firmware selection or successful boot. Its result remains explicitly unqualified.

## Read-only deployment inventory

Run the standalone collector on an existing Linux Pi:

```sh
python3 inventory.py --role terminal > terminal-inventory.json
python3 inventory.py --role server > server-inventory.json
```

Use only the appropriate role. It reads fixed OS/package/service/mount facts and
counts selected application/data trees. It does not invoke sudo, restart a
service, access a camera/audio device, scan a network, or request TV/USB power.
The tree walk is bounded and does not follow links or cross filesystems. An
unreadable, missing or partial tree is recorded explicitly. Sizes are allocated
bytes, not the minimum size of a future image.

Keep raw inventory private: host paths and installed software can reveal local
details even though passwords, network addresses, hostnames, MACs, SSH keys and
service environment/command lines are not deliberately collected. Review before
publishing a sanitized summary. A package inventory of a live Pi is evidence of
that installation, not a trusted reproducible package source lock.

## Offline root inspection

`inspect-root` does not mount disks or execute image code. Supply an already
unpacked/mounted **offline** tree. It reports selected factory identities,
passwords, enrollment/imported data and private configuration, plus unexpected
special files, a missing slot-local package database and the known vendor EEPROM
update service without a `/dev/null` mask. Linked policy parents are reported as
uninspectable. It does not read through
symlinked sensitive parents. A passing report covers this privacy subset only;
it always records `production_qualified: false`. A correct EEPROM service mask
does not authenticate arbitrary boot/recovery firmware. It cannot establish boot safety,
all possible secret locations, services, artifact signatures or call readiness.

## Offline probe disk inspection

`inspect-disk` accepts a regular uncompressed image file, never a disk-device
path or symlink. It reads the protective MBR, verifies primary and backup GPT
header/array CRCs and agreement, bounds table allocation and validates the pinned
six-partition probe labels/order, unique partition identities, nonoverlap and
equal boot/root slot sizes. Use `--sector-size 4096` for a 4 KiB-sector image;
the default is 512. It does not modify the image or inspect filesystem contents.
CRC checks detect corruption, not a maliciously signed/unsigned image. Passing
this subset remains explicitly `production_qualified: false` and does not prove
that either system can boot. Future production layout/schema validation is a
separate gate.

## Authenticated package intake and retained closures

On Linux, download a role's package intent into a **new** isolated cache:

```sh
python3 -m build_tools.images lock-packages server \
  --output /path/to/new/server-intake \
  --debian-keyring /usr/share/keyrings/debian-archive-keyring.gpg \
  --raspberrypi-keyring /path/to/verified/imagegen/keydir/raspberrypi-archive-keyring.gpg

python3 -m build_tools.images verify-packages /path/to/new/server-intake \
  --expected-lock-sha256 <reviewed-lock-file-digest>
```

Use `terminal` for the terminal intent. Supply trusted **public** archive keyrings;
the tool records their hashes and never uses a private release key. Debian and
Raspberry Pi repositories are explicit HTTPS/Trixie sources. APT's state, empty
package-status file, sources, archive cache, configuration and logs are isolated.
`APT_CONFIG` suppresses loading host configuration/hooks before APT initializes.
No package is installed: the only install-subcommand invocation uses
`--download-only`; `dpkg-deb` reads control metadata without running maintainer
scripts. Run as an ordinary user, not with sudo.

The tool verifies signed InRelease metadata, records verified signer fingerprints,
bounds the resolved download count/bytes and checks each retained archive's
SHA-256 against authenticated package metadata. Legacy URI output may include an
MD5 field or omit it; that field is never the authenticity decision. During
archive-key rollover, one valid, unexpired signature from the selected keyring
can coexist with additional unknown signing keys. Unknown-only, bad, expired,
revoked or malformed signature results are rejected.

Keep the accepted lock digest in a reviewed build input. Verification requires
that external digest; a replaced manifest cannot authenticate itself. Retain the
**whole** cache (archives, copied public keyrings, signed metadata and lock file)
immutably. The verifier rejects missing/extra/changed archives or changed audit
metadata. Build from retained bytes after verification, rather than resolving the
same names against today's mirror. APT failure leaves an incomplete directory
without an accepted lock; do not reuse it as a completed intake.

This locks the requested dependency closure only. It does **not** lock every
future image file, build-toolchain/npm/model inputs, provide long-term remote
archive retention or qualify a production image. Those remain separate stages
in the plan. Large downloaded
caches stay outside Git; lock metadata is suitable for review after checking
provenance and policy. Do not publish raw operator logs without review.

Reviewed candidate metadata is retained in `locks/server.json` and
`locks/terminal.json`, anchored by `locks/index.json`. The normal `check` command
rejects dependency intent that has drifted from those reviewed locks, changed
lock bytes, or inconsistent archive counts/sizes. Keep the binary caches outside
Git. A future build must verify its cache using the corresponding reviewed
`sha256` from that index. New intake is a reviewable dependency change, not an
automatic overwrite of the accepted lock.
Git attributes force LF checkout for these content-addressed JSON files on every
platform. Keep those bytes intact; CRLF conversion changes their lock digests.

## Clean-base capture and local build repositories

`capture-base` reads a clean **offline** dpkg status ledger whose SHA-256 the
caller already knows. Review the ledger's image provenance first; a hash alone
does not prove that it came from the selected builder or covers every image file.
Never substitute a live Pi inventory. The parser requires complete installed
records with exact versions and `arm64`/`all` architecture; duplicate packages,
fields, scalar continuations and unfinished package states are rejected. Dpkg's
desired action is distinct from installed state: `purge ok installed` remains an
installed package and is retained. Linked/special/oversized ledger files are
refused before reading. Output creation is exclusive.

```sh
python3 -m build_tools.images capture-base /path/to/clean/status \
  --expected-ledger-sha256 <reviewed-ledger-digest> --output /path/to/new/base-intent.json
python3 -m build_tools.images lock-base --output /path/to/new/base-intake \
  --debian-keyring /usr/share/keyrings/debian-archive-keyring.gpg \
  --raspberrypi-keyring /path/to/verified/imagegen/keydir/raspberrypi-archive-keyring.gpg
python3 -m build_tools.images local-repo \
  --cache /path/to/base-intake <base-lock-sha256> \
  --cache /path/to/server-intake <server-lock-sha256> \
  --output /path/to/new/server-repository
python3 -m unittest tests.adhoc.test_image_base_inputs -v
```

The reviewed capture in `locks/base-intent.json` comes from the selected imagegen
probe's pre-boot ledger. Both original slot ledgers matched. Its 259 exact
installed selections resolve to 259 retained authenticated archives (164,614,914
bytes), anchored by `locks/base.json` and the `base` entry in `locks/index.json`.
`check` rejects changed intent/lock bytes, mismatched source commits, inconsistent
counts/sizes or a closure missing a captured selection. The raw ledger remains
private. An intake refresh is reviewed explicitly; it never updates an accepted
lock silently. The capture is observed intent, not proof of full build closure.

`local-repo` verifies one to three caches using their **external reviewed lock
digests**, rejects conflicting versions/architectures/content and total budgets,
then copies archives into a new directory. It rehashes copies and uses Linux
`dpkg-scanpackages` to generate an index; package identity, path, size and SHA-256
must agree with the locks. Identical dependencies are deduplicated. Archive
copies are separate files, not hard links into mutable caches. A successful
directory contains `Packages`, deterministic `Packages.gz`, `Release`, a
`build-only.list` and `READY.json`; failures have no READY marker and their
incomplete directory must not be consumed. Simple absolute Linux paths are
required so the source line cannot contain injected APT options.

The source uses `trusted=yes` **only for these verified local `file:` inputs**;
the retained upstream intake remains signed. Do not expose this unsigned
repository over HTTP, put its source in a deployed device, or change host APT
configuration. Keep the generated repository read-only during a build and verify
the original caches again before regenerating it. `READY.json` is a completion
record, not a signature or a continuing integrity monitor. No release private
key is used. Combining the reviewed base with each role produced 312 server and
805 terminal archives. Real isolated, file-only APT download tests consumed all
exact selections for both roles without changing host dpkg state. This proves
local APT consumption, **not yet full image-builder consumption**; `probe-config`
still resolves from upstream repositories and is explicitly unqualified.

## Bootloader probe inputs and configuration audit

`bootloader-config` emits a Kconfig fragment, raw-environment settings and the
watchdog/kernel-handoff examples from `bootloader-profile.json`. It writes only a
new ordinary directory. It does not compile, mount, flash, write raw state or
install a watchdog policy. It deliberately omits `boot.scr`, product health
confirmation and factory provisioning; this output is not a bootable image.
The ordinary `probe-config` still uses the upstream native boot experiment and
does **not** incorporate this candidate automatically.

The profile fences the two 64 KiB environment copies to nonoverlapping aligned
ranges before the probe's first partition. It uses the actual pinned source's
`ENV_REDUNDANT` and MMC index/hardware-partition names and disables FAT storage,
device-tree location overrides and software-partition location overrides. Its
compiled default boot command loads only the local common partition's script.
The watchdog fragment enables the BCM2835 driver, servicing and autostart; its
matching handoff examples bound the kernel's wait for userspace and select PID 1
as the runtime owner. These are experimental inputs, not an installed recovery
contract. Qualify the complete firmware/kernel/initramfs/userspace chain.

Use fresh absolute **Linux** cache/build directories outside any Git checkout,
so an ancestor repository cannot supply an unrelated build version. Work as an
ordinary user in the isolated builder, without signing/deployment credentials.
After acquiring the pinned source and emitting the profile, run from that source:

```sh
make O=/path/to/new-build CROSS_COMPILE=aarch64-linux-gnu- rpi_arm64_defconfig
scripts/kconfig/merge_config.sh -m -O /path/to/new-build \
  /path/to/new-build/.config /path/to/bootloader-profile/probe.config
make O=/path/to/new-build CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
```

Back in Zmala's repository, run `inspect-bootloader` on the resolved `.config`
before compiling with `make -j4 O=... CROSS_COMPILE=aarch64-linux-gnu-`. The
inspector detects missing/discarded settings, legacy-name substitutions,
contradictory state stores and address overrides. It checks a bounded regular
Kconfig file, rejects duplicates, and returns a nonzero status on violations.
A passing subset audit does not prove compilation, source provenance, binary
identity or hardware boot; its result states those limits explicitly.

Record the source commit/digest, resolved config, compiler identity, build log,
binary hash and reviewed source-commit `SOURCE_DATE_EPOCH` together. The complete
host toolchain/dependency closure is not locked by this command. Emitting fixed
settings and pinning source bytes is a step towards repeatable builds, not a
claim of end-to-end reproducibility or production qualification.

## Source audit decisions

The native Pi backend at the pinned audit commit uses a temporary file and `mv`
to commit `autoboot.txt` (`set_primary_persistent`), without explicit file/directory
sync or a redundant durable selector. Its sample `rauc-mark-good.service` calls
`rauc status mark-good` after `local-fs.target` without Zmala health/data checks.
Neither file is installed by these tools. The backend remains an audited reference
candidate, **not production-qualified**. Physical power-cut behavior, early
watchdog coverage and confirmation recovery remain release blockers.

The exact reviewed upstream files can be inspected from the acquired trees:

- `bootloader-custom-backend` and `rauc-mark-good.service` in the backend source.
- `image/gpt/ab_userdata/image.d/hooks/preimage10-slots` in imagegen, including its
  per-slot `/var` and persistent journal behavior, which differs from Zmala's plan.

The alternative boot-state investigation is tracked in
[#149](https://github.com/toastfr35/ZmalaCall/issues/149). A private U-Boot experiment
has compiled and completed an A/B selection, fallback and manual counter-reset
sequence on a Pi. Further private checks exercised healthy watchdog handoff,
a controlled pre-root stall, one newer-copy CRC fault and one operator power cut
during repeated commits. See the plan for measured scope and remaining gates.
It is not included by `probe-config`, acquired by `fetch`, or
adopted as the production backend. The current source's configuration names differ
from older RAUC examples; validate the resolved settings, not just a fragment.
Source references for that investigation:

- [U-Boot v2026.10 environment configuration](https://github.com/u-boot/u-boot/blob/5508406582f6f7120dce0c4b3059819a41788db2/env/Kconfig).
- [U-Boot v2026.10 Pi ARM64 defaults](https://github.com/u-boot/u-boot/blob/5508406582f6f7120dce0c4b3059819a41788db2/configs/rpi_arm64_defconfig).
- [RAUC 1.13 bootloader integration](https://rauc.readthedocs.io/en/v1.13/integration.html#u-boot).

Deterministic environment-library tests using ordinary files do not demonstrate
physical SD durability, the bootloader's selection, early-watchdog recovery, or
firmware/kernel compatibility. The private hardware checks add initial recovery evidence,
but do not establish the complete power-cut matrix or product health-confirmation
recovery. Those
remain hardware and architecture gates.

The private kernel handoff also exposed low-memory fragmentation: U-Boot's default
placement split the graphics CMA window, leaving too little contiguous memory for
the framebuffer. Setting explicit bounded FDT and initrd relocation ceilings
restored the full pool and HDMI in that experiment. Future image integration must
qualify the complete memory map and payload sizes on supported boards, rather than
copy an address from one Pi. See the implementation log for measured scope.

Product runtime requirements and user installation guides remain unchanged until
the runtime/image installation flows are implemented. Image-tool regressions live
under `tests/adhoc/` and run independently of requirement-based runtime tests.
