# SD-card images and Raspberry Pi Imager: work left

Checkpoint: **7 November 2026**. This is an implementation and qualification
checklist, not a new product requirements baseline or a declaration that images
are ready for distribution. Runtime requirements remain in [requirements/](requirements/).

Use this as the short continuation list. The detailed design is in
[update_upgrade.md](update_upgrade.md), historical evidence and private artifact
catalog names are in [upgrade_system_status.md](upgrade_system_status.md), and
build commands are documented in [zmala_images/README.md](zmala_images/README.md).

## Current position

- Offline package intake, application provisioning, initramfs construction and
  complete development-media assembly exist for terminal, server and combined roles.
- The repaired **older 32 GB-layout test card** boots into Zmala. The user confirmed
  Bluetooth/remote tests, Wi-Fi connection and server enrollment using a fresh QR.
  Bluetooth uses a private firmware-device-tree diagnostic. The Wi-Fi backend and
  QR feedback repairs on that card were applied in RAM and disappear on reboot.
- Source fixes cover initramfs dispatch (#175), compact media (#177), QR feedback
  (#179), the missing Wi-Fi backend (#181), and Argon fan configuration (#183).
  PR integration and normal application releases do not qualify an SD image.
- **Terminal and terminal+server images always use the Argon ONE Pi 4 V2 case.**
  There is no optional image-build case flag. The fan policy remains off outside
  connected calls, 55% during calls and 100% at 65°C during calls. The image fix
  includes I2C access and boot configuration; physical fan transitions are unverified.
- An earlier compact terminal image passed regular-file 16 GB/32 GB geometry and
  filesystem checks. It predates the permanent Wi-Fi and fan corrections and is
  not the next card-write candidate. No physical compact-card boot is recorded.
- At this checkpoint the corrected locked Wi-Fi OS root is still building. Its
  continuation pipeline waits for an accepted `READY.json`, then provisions the
  mandatory Argon terminal and constructs the compact image. A running build is
  not an accepted artifact; inspect its result before starting another one.

## 1. Finish the next terminal test candidate

- [ ] Accept the corrected OS root only after its package-ledger audit, final
  `READY.json` and independently checked digest. Preserve failed logs and reject
  incomplete outputs. Reuse authenticated caches and unchanged accepted roots.
- [ ] Complete application provisioning, storage preparation, initramfs and disk
  assembly from one recorded source commit. Record package locks, builder/input
  hashes, application version, kernel and output hashes; explain any difference
  between the candidate source and subsequently merged documentation-only changes.
- [ ] Verify the target Wi-Fi supplicant loads with all its libraries, D-Bus policy
  and activation unit, and that NetworkManager can start it on an ordinary boot.
- [ ] Verify mandatory Argon configuration in the root, terminal account, module
  loading, device permissions, firmware configuration and both boot-slot trees.
- [ ] Preserve the working Bluetooth behavior in a clearly labelled development
  candidate. If the private full-firmware-tree diagnostic is used again, retain
  the original script and record the changed image hash separately. It is not a
  production A/B device-tree solution.
- [ ] Recheck GPT/FAT/ext4 structure, boot-slot payloads, initramfs dispatch and
  application/unit checks on the final artifact, rather than an earlier image.
- [ ] Confirm the final raw image fits the actual target card byte capacities.
  Validate the final image's first-boot GPT relocation on 16 GB and 32 GB media,
  unchanged partition extents/IDs and repeat-boot no-op behavior.

## 2. Run the next physical card test

- [ ] Arrange the card return only when the complete candidate is ready. Preserve
  the known working card/backup and freshly verify the reader's device identity,
  exact capacity and intended target before any write. A previous drive letter
  is not sufficient identification.
- [ ] Flash and verify the exact candidate. Record the writer/tool, image hash,
  actual medium capacity and readback result. Keep private diagnostics out of
  any image intended for users.
- [ ] Cold-boot **a real 16 GB card and a real 32 GB card**, recording each result.
  A sparse-file capacity test is not a physical SD-card or power-loss test.
- [ ] Confirm setup without the temporary RAM repairs: Bluetooth pairing/remote,
  Wi-Fi join, a current HTTPS server QR, TV/display, camera, microphone and speaker.
- [ ] Test the QR guide colour change and specific failure feedback for invalid
  QR, missing SSID and rejected credentials, then retry successfully. Do not
  treat every authentication failure as proof of a wrong password.
- [ ] Make and end a real call. Confirm fan off during setup/idle, on during the
  call and off after hangup. Cover service shutdown/restart and the temperature
  threshold separately; a passed unit test is not physical fan evidence.
- [ ] Reboot and power-cycle again. Confirm saved Wi-Fi/server enrollment and
  Bluetooth state persist, setup does not restart unexpectedly, and no SSH
  diagnostic or RAM repair is needed for ordinary operation.
- [ ] Record kernel/storage errors and voltage/throttling state during tests.
  Earlier undervoltage was observed; its significance is not yet established.

## 3. Measure actual storage and capacity margins

Current compact layout: **14,001,635,328 raw bytes**, with a 32 MiB common boot
partition, two 512 MiB slot boot partitions, two 4 GiB root partitions and a fixed
4 GiB data partition, plus alignment/GPT allowances. Extra space on larger cards
stays unallocated. GPT relocation does not expand a partition or filesystem.

Earlier measurements are reference evidence only: the previous compact terminal
root had **1,804,566,528 bytes free per slot**, and data had **4,143,648,768 bytes
free**. Disposable older combined filesystems fitted 4 GiB with **1,675,853,824
bytes free**. These do not measure the newly corrected candidate.

- [ ] Measure allocated/used/free bytes in every filesystem of each newly built
  terminal, server and combined artifact, including both root slots.
- [ ] Record raw and compressed download sizes, package/source version and actual
  16 GB/32 GB card capacities. Marketed card sizes are not exact byte guarantees.
- [ ] Measure peak persistent-data usage during staging, download, verification,
  rollback-compatible migration, diagnostics and retained history. Confirm update
  headroom on the smallest supported card, not just factory-image fit.
- [ ] Set and document a minimum supported device capacity from those results.
  Decide whether later optional data expansion is useful; it is not part of the
  current compact candidate and must not be implied by the 32 GB compatibility claim.

## 4. Remove development-only boot and onboarding gaps

- [ ] Replace the Bluetooth diagnostic with a qualified slot-matched DTB/overlay
  design. Investigate the observed UART RTS/CTS pin/pull differences and other
  firmware fixups; isolate the necessary correction rather than assuming that
  one difference explains all hardware behavior.
- [ ] Qualify both boot slots, payload mismatch/failure handling, common-loader
  compatibility and firmware fixups across supported OS generations.
- [ ] Build and boot the corrected **server-only** and **terminal+server** images.
  Combined package/runtime foundations exist; complete role-specific hardware
  qualification and resource measurements still remain.
- [ ] Finish server first-owner claiming, HTTPS/TLS and network onboarding without
  an ordinary SSH installation step. Verify combined onboarding, separate private
  state and recovery after interrupted setup.
- [ ] Finish supported diagnostic/recovery access without a shared factory password
  or private key. The lab's one-boot Ethernet SSH window is not a release feature.

## 5. Deliver images through Raspberry Pi Imager

- [ ] Produce compressed, immutable, role-labelled terminal/server/combined image
  artifacts with checksums, authenticity verification, provenance and licences.
  Keep image binaries out of Git and signing credentials in the release workflow.
- [ ] Test Raspberry Pi Imager's **custom-image** route end to end, including
  write verification and first boot. This is the planned baseline; a custom
  Imager catalogue is later work, not a prerequisite for another private card test.
- [ ] Test/document Imager behaviour on Windows, macOS and Linux. Decide which
  OS-customisation settings are supported, ignored or disabled so they cannot
  overwrite appliance users, networking, mount policy or partition geometry.
- [ ] Measure compressed artifacts against the chosen host's current limits and
  verify download/resume/integrity behaviour. Select a suitable immutable host
  if needed; avoid a normal user workflow that requires joining arbitrary chunks.
- [ ] Update release collection/validation for all three image choices and their
  trust materials. Account for existing app-update assets and the leaflet ZIP;
  do not silently break legacy clients or assume a fixed nine-file release.
- [ ] Regenerate the affected Word/PDF installation guides and authoring sources
  for download, Imager, card selection, first boot and recovery. Validate fresh
  installation using only published artifacts and those instructions.
- [ ] Retain supported legacy installers until the replacement workflow and
  migration/rollback procedure are qualified. Then change the public download
  links deliberately; do not present current development images as ready releases.

## 6. Broader system-update work remains separate

A flashable first-install image does not finish the OS-upgrade project. Track the
following in [the detailed update plan](update_upgrade.md), without holding up
another clearly identified development-card test:

- [ ] Signed system feed/bundles, trust rotation, bounded staging and one durable
  inactive-slot install/trial/confirm/rollback transaction.
- [ ] Kernel-to-userspace watchdog handover and local product-health confirmation,
  including combined-role health and normal offline/setup conditions.
- [ ] Call-safe terminal admission, server-wide SIP/TURN idle admission, combined
  coordination, visible progress and durable TV restoration.
- [ ] Rollback-readable data migration, retained-card/import recovery, real A→B→A
  tests, interrupted writes/power cuts and at least one different-major-OS upgrade.
- [ ] Three-role soak, thermal/performance/storage qualification and controlled
  beta promotion before broad distribution or automatic fleet updates.

## Evidence and completion discipline

For each checked item, retain the exact source/artifact identity, environment,
procedure and result. Link actual hardware results separately from QEMU user-mode,
namespace, mocked and regular-file tests: no full Raspberry Pi board simulator
is currently qualifying these images. Keep packaging checks in `tests/adhoc/`
and runtime verification linked to the existing requirements. Do not mark a
planned, skipped or manual hardware scenario as passed.
