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
python3 -m build_tools.images inspect-root /path/to/offline/root
python3 -m unittest tests.adhoc.test_image_foundation -v
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

`profiles.json` records the common base and role package **intent**, not a complete
resolved package lock. The terminal intent reuses the existing dependency list;
server npm/build dependencies and full secure-relay provisioning remain to be
separated into build/runtime sets. The selected RAUC package is Debian Trixie's
`1.13-3+deb13u1`; availability and exact transitive package/archive inputs still
need to be locked before production builds.

The emitted `probe.yaml` is a minimal Pi 4 A/B **boot experiment**. It does not
install Zmala, a bootloader backend, production keys or an update coordinator.
`package-intent.txt` is separate from the minimal probe package list. Its adjacent
`status.json` explicitly records missing package locking, product provisioning,
boot safety and hardware qualification. Nothing here publishes or promotes it.

After fetching, the upstream configuration resolver can check each probe:

```sh
# Replace <commit> with the imagegen commit in sources.lock.json.
build_tools/tmp/image-sources/imagegen-<commit>/rpi-image-gen config \
  build_tools/tmp/terminal-probe/probe.yaml \
  --write-to build_tools/tmp/terminal-probe/resolved.env
```

The upstream `image-rota` probe layer uses its own selector partition size and
persistent `/var` policy. Those are acceptable subjects of a boot experiment,
not adopted production storage policy. In particular, its per-slot persistent
package database cannot be reused unchanged across replacement root images.
The custom narrow persistent mounts and qualified selector are still required.

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
special files and a missing slot-local package database. It does not read through
symlinked sensitive parents. A passing report covers this privacy subset only;
it always records `production_qualified: false`. It cannot establish boot safety,
all possible secret locations, services, artifact signatures or call readiness.

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

Product runtime requirements and user installation guides remain unchanged until
the runtime/image installation flows are implemented. Image-tool regressions live
under `tests/adhoc/` and run independently of requirement-based runtime tests.
