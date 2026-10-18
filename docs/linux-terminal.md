# Linux terminal

For the Pi 3 and Pi 4 hardware codec probes and integration assessment, see
[hardware video investigation](pi-hardware-video.md).

ZmalaCall uses one Python terminal implementation for Windows and Linux. Call
states, server communication, contacts, translations, carousel animation,
notifications, confirmations and provisioning flow are shared. Operating-system
adapters live under `zmala_terminal/linux/`; shared code is in `common/`. Windows launchers and its native
SDK remain available for testing on the PC.

## Install

The reusable installer targets **Raspberry Pi 4 Model B, Raspberry Pi OS Lite
64-bit (Debian 13 Trixie)**. Start with a standard image; no desktop, cloned
terminal data or preconfigured Wi-Fi is required. Connect Ethernet with Internet
access, the HDMI TV, and the Nuroum C20. In Raspberry Pi Imager, enable SSH
with password authentication and set the hostname, username and password all
to `zmala`. The installer defaults to this account; SSH connects to
`zmala@zmala.local` with password `zmala`. Choose the correct Wi-Fi country even when
leaving the SSID/password empty. The installer supplies Xorg, Openbox, Picom,
BlueZ, NetworkManager, Liblinphone, native media plugins and the local framing
runtime/model. Downloads need Internet access; calls do not download models.

### Windows installer (recommended)

The illustrated fresh-card installation guide is available as an
[editable Word document](../output/docx/ZmalaCall-Pi4-Installation-Guide.docx)
and [PDF](../output/pdf/ZmalaCall-Pi4-Installation-Guide.pdf).
It includes the Imager settings, Argon case connections and remote/QR setup.

Download the installer and guide from the
[latest public release](https://github.com/toastfr35/ZmalaCall/releases/latest);
no GitHub sign-in is required. For an unreleased build, sign in and download the
artifact from a successful [Build terminal installer workflow](https://github.com/toastfr35/ZmalaCall/actions/workflows/build-terminal-installer.yml)
run. Extract the archive and run **`zmala_terminal_setup.exe`** on Windows.

1. The Pi hostname is `zmala`; its local network address is `zmala.local`.
   Leave that address in the installer, or enter its Ethernet IP if name
   resolution fails. The login/password are both `zmala`.
2. Click **Check Pi**. It verifies SSH login, sudo access, Raspberry Pi 4 hardware,
   the Raspberry Pi OS image marker, Trixie/ARM64, mounted boot partition, free
   space, and that SSH is connected to the Ethernet address.
3. Click **Install** and confirm the displayed target. The Windows installer
   always includes Argon ONE V2 fan setup; there is no case selection.

The installer uploads and verifies the embedded package, runs the Linux
installer, reboots, reconnects to the same SSH host key and checks that the
terminal and supporting services stay active. It retains the verified Ethernet
address during deployment, so Wi-Fi advertisements after reboot cannot redirect
its SSH connection. Existing enrollment is preserved.
Installation runs as a separate systemd job, so a brief Windows/network
disconnection does not terminate it. The Windows app retries interrupted SSH
connections. If the connection cannot be recovered, its error includes the Pi
installation output location; do not assume the remote job stopped.

Status appears in the main window; **View details** shows live installation
output and errors. **Open saved log** in that window opens the saved PC
log under `%LOCALAPPDATA%\ZmalaCall\Installer\logs`. The detailed Pi log is also
retained in `/var/log/zmalacall-install/`. The final success message requires a
new boot ID and stable services after reboot. Physical HDMI picture, sound and
QR enrollment still require the first-run TV setup.

The locally built executable is unsigned. Builds require Windows Python with
Tk support (only on the development PC):

```powershell
python -m pip install -r build_tools/windows_installer/requirements.txt
python build_tools/windows_installer/build.py
```

The build embeds a fresh terminal archive and writes `build_tools/dist/zmala_terminal_setup.exe`.
GitHub Actions builds and smoke-tests the same executable on Windows when
installer, terminal or documentation files change on `main`. Use **Run workflow**
on the workflow page for a manual rebuild. Artifacts are retained for 90 days;
if the last successful build has expired, run the workflow again. The CI smoke
test opens the packaged UI and verifies its payload without connecting to a Pi.

### Unattended Windows installation

The same `zmala_terminal_setup.exe` supports installation without a graphical
window. `--headless --yes` confirms installation and the automatic reboot;
all SSH, OS, wired-network, package and startup checks still run. Argon fan setup
is always enabled. The Pi must already have the flashed image and Ethernet
connection described above. QR enrollment still follows on the terminal.

Because the EXE is a Windows GUI executable, scripts should wait explicitly
and inspect its process exit code:

```powershell
$setup = Start-Process -FilePath .\zmala_terminal_setup.exe `
    -ArgumentList '--headless', '--host', 'zmala.local', '--yes', `
                  '--log', 'C:\Temp\zmala-install.log' `
    -Wait -PassThru
$setup.ExitCode
Get-Content C:\Temp\zmala-install.log
```

Use `--check-only` instead of `--yes` for a read-only preflight. If mDNS cannot
find the Pi, replace `zmala.local` with its Ethernet IP. Without `--log`, logs
are written under `%LOCALAPPDATA%\ZmalaCall\Installer\logs\headless-*.log`.
Progress is flushed to the file throughout installation; standard output is
also used when available. No dialog or interactive input is required.

Exit codes: **0** success, **1** installation/check/log failure, **2** invalid
arguments or missing `--yes`, **130** interrupted. Success after an install
means the reboot and service checks passed. If interrupted or disconnected,
the Pi installation job can continue; inspect its reported log before retrying.
GitHub tests both GUI and headless packaged modes before uploading an artifact.

### Manual installation (alternative)

Build the same package for every terminal on the PC:

```powershell
python build_tools/linux/package-terminal.py
scp build_tools/dist/ZmalaCall-Terminal-rpi.tar.gz* zmala@zmala.local:~/
```

Run over **Ethernet** on the new Pi:

```sh
sha256sum --check ZmalaCall-Terminal-rpi.tar.gz.sha256
mkdir -p ~/zmala-install
tar -xzf ~/ZmalaCall-Terminal-rpi.tar.gz -C ~/zmala-install
cd ~/zmala-install
sudo ./install.sh
sudo reboot
```

The archive includes a SHA-256 manifest checked before installation. Its
checksum sidecar detects transfer corruption, not an untrusted publisher.
Every installation saves a private log in `/var/log/zmalacall-install/` and
prints its path. Failures stop installation with a nonzero exit code and the
failed stage (dependencies, SSH, media build, boot screen, startup, etc.). The
installer checks the OS, boot partition mount, archive checksums, free space
(3 GiB on `/var`, 128 MiB on `/boot/firmware`), and service health. Package-index
download errors are fatal rather than silently using stale indexes. Startup
checks include the compositor, CEC observer, SSH guard and network services;
restarts during the observation window are failures.

If installation fails, keep Ethernet connected, inspect the reported log with
`sudo less /var/log/zmalacall-install/install-....log`, fix the reported cause,
and rerun the same command. Retrying preserves enrollment. OS/package changes
are not automatically rolled back. The log cannot record events after sudden
power loss. A successful install still needs the first-boot hardware/QR test;
an absent camera or unpaired remote is an expected setup state, not a failure.

The installer requires an active physical Ethernet interface, defaults to
`eth0`, and supports `--ssh-interface NAME` for another wired interface.
**After installation SSH is available only over that interface**, regardless
of DHCP address. An nftables `inet` input rule drops SSH arriving through
Wi-Fi, loopback, or other interfaces, including IPv6 and traffic addressed to
the Ethernet IP but received on Wi-Fi. Existing SSH authentication is retained.
Port 22 (including socket activation) and configured sshd ports are covered;
sshd restart regenerates the rule if its ports change. SSH startup requires
the guard and firewall services. Normal nftables reloads retain the rule via
an include; do not remove that include or manually flush the ruleset.
The installer owns only `inet zmala_ssh`; it does not replace other firewall
configuration. Use this on the dedicated stock image, not as a general firewall
migration tool. Keep Ethernet connected for administration after Wi-Fi setup.

### Argon ONE Pi 4 V2 case

For a Pi in this case, install with `sudo ./install.sh --argon-one`
and reboot once to enable I2C. The terminal controls only the fan: off while
idle, setting up, ringing or calling an unanswered contact; 55% duty cycle
while a call is connected, increasing to 100% at 65°C. It stops at hang-up.
I2C writes and temperature reads run on a worker, outside the media/UI loop.
A systemd stop hook also requests fan-off after an app crash. The requested
call-only policy has no temperature override outside calls; the Pi retains
its own firmware thermal throttling. Monitor temperatures when changing the
workload or enclosure. The case may briefly spin the fan before software starts.

This uses the vendor's [ONE I2C protocol](https://github.com/Argon40Tech/Argon-ONE-i2c-Codes):
only fan duty values 0–100 are written to bus 1, address 0x1a. Power-mode and
shutdown commands are never sent. The installer does not install the vendor's
power-button/IR software, and refuses to compete with an enabled `argononed`
controller. The option is specific to the Pi 4 V2 case, not a generic Pi 5 fan
interface. Keep `--argon-one` on repeat installation commands for this case.

### SD-card write reduction

The installer enables these settings automatically:

- The terminal and QR-camera diagnostics go to the system journal in RAM.
  The journal is limited to 64 MiB, with 8 MiB files and rate limiting. Syslog
  forwarding is disabled so a second logger cannot copy those messages to disk.
- Swap uses compressed RAM (zram), capped at 2 GiB of virtual capacity, with
  no SD-backed writeback file. The change takes effect at the installer reboot;
  installation never runs `swapoff` against a live workload.
- Installed-terminal lock and PID files live in private `/run/zmalacall`.
  Pairing and CEC status already use `/run`. The stock image's RAM-backed `/tmp`
  and `noatime` root mount are checked after reboot.
- Enrollment, Wi-Fi and Bluetooth pairing, settings, missed calls, media
  security databases and downloaded photos remain persistent. Configuration
  caching already skips unchanged data and excludes live presence/callbacks.

Routine diagnostics are lost at reboot. Export them to the Windows PC before
restarting when troubleshooting. Installer logs remain persistent for recovery;
existing application logs are retained but are no longer appended by the kiosk.
Detailed Python diagnostics are normally suppressed. Enable them temporarily
without restarting the app (10 minutes by default, at most 60):

```sh
python3 /opt/zmalacall/current/build_tools/linux/diagnostics.py 10
sudo journalctl -u zmalacall-terminal -f
```

Use `diagnostics.py 0` to stop early. The flag expires automatically and is also
discarded on terminal restart or reboot. The Windows installer verifies these
storage settings after reboot before reporting success. They can also be checked
with `python3 /opt/zmalacall/current/build_tools/linux/check-low-wear.py`.

The root filesystem remains writable, with its normal journaling. A read-only
root/overlay is deferred: it requires a separate persistence and update design
for QR enrollment, Wi-Fi, Bluetooth and terminal settings.

Validation on the Argon Pi 4 (`zmala`, 17 October 2026): a 180-second call with
the real C20, automatic framing, and a moving test pattern from Windows
negotiated 1920×1080 in both directions. Final rates were about 15 fps each;
minimum received rate after startup was 11.54 fps. During the overlapping
206-second memory/write observation, available RAM stayed above 2297 MiB,
terminal-process proportional memory peaked at 290 MiB, swap usage stayed zero,
and the kernel recorded no OOM kills. Whole-card writes were 564 KiB; the only
changed files under terminal state were Liblinphone and media-security databases.
The old terminal/QR log files and configuration cache did not change. This is a
short operational test, not a lifetime-wear estimate or memory-exhaustion test.
Stock Pi OS disables the memory cgroup controller; measurements use process PSS
and system memory counters without changing that kernel setting.

Enrollment, Wi-Fi credentials and Bluetooth pairing were checked by hashes
across reboot. A one-minute debug window produced framing diagnostics and then
stopped automatically while the call continued. Normal audio levels were restored.

### First startup and identity

Installation screens stay in English until server enrollment applies the
terminal's selected language. Before Bluetooth pairing, a missing Nuroum C20
shows the illustrated USB guide: camera into a blue USB 3 socket, remote charger
into the adjacent black socket. It advances automatically when the C20 appears.
The charger itself cannot be detected. This gate is limited to enrollment and
does not interrupt an enrolled terminal or an active call.

1. If no Presenter+ is paired, the TV shows pairing instructions. Switch the
   remote on and hold its rear Bluetooth button for three seconds until the
   white light flashes. The terminal pairs and trusts it automatically. Only
   a single advertising Microsoft Presenter+ with the HID service is selected;
   other device types and ambiguous multiple matches are ignored. This is a
   nearby physical setup procedure, not a cryptographic device-name check.
2. Complete the on-screen remote test: press and release Left, Right,
   Green, Red, then Middle (the Pointer button), in that order. Only actual
   Presenter input counts; a keyboard cannot pass the test. Calls and volume
   changes are suppressed during the test. All five buttons must pass before
   QR scanning starts. A disconnect resets unfinished progress. Success is
   saved for this Bluetooth pairing across reboots; pairing again or a factory
   reset requires a new test. Power and pairing buttons are not tested because
   they interrupt the Bluetooth connection.
3. Show the camera the Wi-Fi QR. NetworkManager stores the credentials locally;
   no Wi-Fi credentials are embedded in the installer. The camera stays closed
   until pairing and the button test are complete and input is connected. If already paired but switched off, the remote's
   normal power/charging help is used instead of pairing it again.
4. Show the **server QR**. Its existing version-1 payload already contains
   `server_url`, **`device_id`** and `device_token`. The displayed terminal serial
   is this server-assigned ID, not the Pi serial, hostname or installer username.
   A fresh install has no terminal identity until this QR is accepted.
5. Complete the TV-control checks after enrollment, in the selected language
   (currently English/French prompts; other languages fall back to English).
   Green starts the power test; confirm whether the TV went off and on. Then
   select live TV or another HDMI input with the TV remote when prompted.
   Confirm the ZmalaCall → previous source → ZmalaCall round trip. If the
   picture does not return within 30 seconds, select the terminal input manually.
   Failed checks offer help and retry, or continuation with manual TV control.

To replace term2, stop and disable the old terminal before scanning its existing
server QR on the new Pi. No QR format change or reprint is needed if the URL and
credentials remain valid. A regenerated/revoked token, deleted account or changed
server URL requires a current QR. Two running terminals must not share one QR.
Bluetooth pairing and any Samsung network-remote permission are specific to the
new Pi; they are not copied from a reference device.

The terminal starts immediately and at boot without console login. A Plymouth
screen with the Zmala logo over a subdued multilingual “family” word cloud
replaces normal boot messages; firmware/HDMI negotiation can still cause
brief blank screens. HDMI defaults to 1280×720 near 60 Hz when advertised
by the TV, avoiding a 4K desktop on the Pi. `--display-mode 1920x1080` selects
1080p; `--display-mode auto` keeps Xorg’s choice. This is independent of the
server’s call-video resolution. `--no-splash` leaves boot presentation unchanged. The
original boot files are saved as `*.before-zmala`; kernel disk, network and
HDMI arguments are preserved. A rescue console remains available on other VTs.
The optional `--without-framing` skips the detector download and environment;
leave automatic framing disabled in the server for such installs.

The service runs as the specified non-root user (created if absent); an existing
login account keeps its password and shell. The kiosk owns X display `:0` and
VT7 and disables a desktop display manager if present. Runtime state remains in
`/var/lib/zmalacall` (private to the service user); code is root-owned under
`/opt/zmalacall/releases`. Upgrades use the same command, retain enrollment,
Wi-Fi, pairing, settings and photos, and switch `current` only after compiling
media and installing dependencies. `previous` retains the prior release for
recovery. The installer rejects concurrent runs. A failed health check reports
an error; it does not erase enrollment or automatically roll back OS packages.

For an explicit migration, `--data-from /path/to/old/data` copies missing state;
`--bootstrap /path/to/terminal.json` supports administrator enrollment without
a camera. **Neither option is needed for a fresh QR-based deployment.**
`--wifi-mode existing-link` is only for development that deliberately bypasses
joining the QR's Wi-Fi network.

Check the installation:

```sh
systemctl status zmalacall-terminal zmalacall-display zmalacall-pairing
sudo nft list table inet zmala_ssh
sudo journalctl -u zmalacall-terminal -u zmalacall-pairing -b
```

For the later clean-SD acceptance test, reflash the same standard OS image,
copy this archive, run the commands above, and verify pairing → Wi-Fi QR →
server QR → TV checks without manually copying any runtime files. Reboot again after
enrollment to verify retained identity, remote reconnection and automatic startup.

Use the system `python3`: the apt-installed GI, Cairo, Tk and OpenCV modules are
not automatically visible in a pip virtual environment. Installation adds the
packaged Liblinphone 5.3 runtime and OpenH264. OpenGL development packages supply
the unversioned library names dynamically loaded by that media runtime.

The server may run on Windows or a separate Pi. Restart it after installing LAN API
change. Its HTTP listener accepts authenticated terminal requests over the LAN;
administration supports LAN browsers using the shared admin password, including
first-time setup. See [administration authentication](admin-authentication.md).
Allow Node.js through the
PC's private-network firewall for HTTP, SIP and media. Server QR downloads use
the PC's LAN address. Keep that address stable, for example using a DHCP reservation.

## Start and stop

For the installed kiosk:

```sh
sudo systemctl status zmalacall-terminal
sudo systemctl restart zmalacall-terminal
sudo systemctl stop zmalacall-terminal zmalacall-display
sudo systemctl start zmalacall-display
sudo journalctl -u zmalacall-terminal -u zmalacall-display -b
```

To disable automatic startup, run
`sudo systemctl disable --now zmalacall-terminal zmalacall-display`.
Both services restart after failures; stopping them explicitly leaves them stopped.
The separate `zmalacall-compositor` service starts with the display and stops
or restarts with it. Picom uses XRender with VSync, without shadows or fades,
and keeps fullscreen terminal/video windows composed. Tk already buffers its
canvas drawing; synchronized presentation addresses tearing when those canvas
updates reach HDMI. The compositor restarts independently if it fails, so its
failure does not stop calls. Inspect it with
`journalctl -u zmalacall-compositor -b`.
On Raspberry Pi 4 with Raspberry Pi OS's `msdri3`-capable Xorg driver, the
installer also installs `/etc/X11/xorg.conf.d/21-zmalacall-pi4.conf`. This selects
`AccelMethod "msdri3"`: X11 drawing uses software rendering while native video
retains DRI3 access. On the tested Pi, Glamor's compositor buffers failed KMS
import (`Present-flip: Import BO failed`), forcing copies despite VSync. The
alternate path allowed synchronized page flips and eliminated visible tearing.
This override is board/driver-specific; remove it when moving an installed SD
card to another board or to an Xorg build without `msdri3` support. Do not add
`TearFree` to this Xorg 21.1 driver: it does not implement that option.
The top-right Bluetooth symbol reports Presenter input availability: green
when its input devices are open, red with a slash when unavailable, and grey
where monitoring is unsupported (including Windows). It updates when Linux
removes or rediscovers the device; it does not claim that the TV input is ready.
CEC adapter selection prefers a detected display with EDID, then enabled
scanout, so a boot-forced empty HDMI port cannot trap the routing observer.
The first press with unknown/hidden TV routing may be consumed to select the
terminal input and allow HDMI to settle; subsequent visible-terminal presses
use the cached routing state.

Display blanking is disabled while the kiosk runs. Incoming calls save the TV's
observed power and source before CEC wake/input selection. Rejecting restores
that state; accepting retains it until the call ends. If the TV is already on
and displaying the terminal, no source/power changes are sent. Volume and mute
remain untouched. Restoration is best-effort when the TV does not report its
previous source; the terminal never guesses an input.
On boards with two HDMI ports, the terminal and CEC observer select the adapter
mapped by the kernel to a connected HDMI output. An explicitly configured
observer `--device` remains fixed. If neither port reports a connection, the
current adapter is retained so a standby TV can still be woken. A saved TV
restoration is never redirected to another adapter during a call.
The physical Xorg session hides the mouse pointer. Linux video availability uses
the decoder's received frame rate, avoiding unsupported next-frame notification
methods in the distribution's OpenH264 plugin.

### Moving a Pi 3 card to a Pi 4

Use HDMI0 (nearest USB-C power) for the initial display check. With the TV on
and its input selected, inspect `cat /sys/class/drm/card*-HDMI-A-*/status`.
If both outputs say `disconnected`, inspect the micro-HDMI cable/adapter and
TV connection before changing the terminal application. A running Xorg server
with a virtual framebuffer is not proof of an HDMI picture. Keep the KMS
driver (`dtoverlay=vc4-kms-v3d`); the tested Pi 4 uses the same hardware encoder
interface as the Pi 3 and does not require another media backend.

On the migrated Pi 4, a runtime-only forced signal did not restore the TV
picture, but a forced mode applied at boot did. For this KMS setup, back up
`/boot/firmware/cmdline.txt` and append `video=HDMI-A-1:1280x720@60D` to its
existing single line to force HDMI0 at 720p/60 Hz, then reboot. Do not replace
the root-device or other existing boot arguments. This is a device-specific
troubleshooting override, not an installer default; force only the port in use.
The `hdmi_safe`, `hdmi_group` and `hdmi_mode` settings belong to the legacy
display configuration. See the [official KMS display instructions](https://www.raspberrypi.com/documentation/computers/configuration.html#set-the-kms-display-mode).

Check `vcgencmd get_throttled` and the kernel journal under call load after
changing the board or power supply. Record power faults separately from codec
or network failures; a successful idle boot does not establish stable power.

The following launchers remain useful for source-tree development, inside an
existing X11 desktop session (not alongside the installed kiosk):

```sh
cd ~/zmalacall
./build_tools/linux/start-terminal.sh --fullscreen
./build_tools/linux/stop-terminal.sh
```

Each instance has a separate profile, enrollment, SIP databases and process lock.
An unconfigured test instance uses the `unconfigured` profile:

```sh
./build_tools/linux/start-terminal-unconfigured.sh --fullscreen --wifi-mode connect
./build_tools/linux/stop-terminal.sh --profile unconfigured
```

The start scripts detach the application and keep startup output in
`zmala_terminal/data/<profile>-startup.log`. Normal diagnostics are in
`zmala_terminal/data/terminal.log`; QR worker errors are in
`zmala_terminal/data/qr-camera-error.log`. Stop checks process identity and stops
only the selected profile. The application closes its camera worker and command
processes when it exits.

For direct foreground diagnostics:

```sh
python3 -m zmala_terminal.common.main --profile terminal --fullscreen
```

## Configure and use

### Microsoft Presenter+

Pair the remote directly with the Pi over Bluetooth; the USB dock charges it.
When Presenter input is unavailable for five seconds, the idle carousel is
covered by a recovery page. It clears automatically when the input devices
return. Incoming/active calls and enrollment retain priority; the page does not
wake the TV. Windows keyboard terminals do not display this page.

Read-only, bounded BlueZ checks run on a background worker. The page distinguishes
a missing saved pairing, a disabled/missing adapter, a blocked remote, and a
Bluetooth connection whose input controls are not ready. A paired but disconnected
remote may be off, out of range, uncharged, or faulty: Bluetooth does not establish
which. On installed kiosks the separate `zmalacall-pairing` service enables
Bluetooth and pairs automatically when there is no saved Presenter. The first-run
pairing page takes priority over enrollment, but never over a call. Turn-over instructions and the picture's Front,
Back and On/Off labels follow the selected language, with translations for all
selectable languages in `shared/remote-orientation.json`. These labels are drawn
over text-free artwork using the terminal's font/shaping renderer and change
with the UI language. Detailed Bluetooth diagnostic copy is available in English
and French, with an explicit English fallback for other terminal languages.
The disconnected-remote instructions ask the user to switch it on, then charge
it in its powered dock if it remains disconnected. A flat battery is presented
as a possibility, not a measured condition; no button press is required.
The battery icon immediately left of Bluetooth shows the connected Presenter's
reported charge: green above 20%, amber at 11–20%, red at 0–10%. A grey question
mark means no current reading (including disconnected remotes). Battery status
shares the five-second background check and expires after 20 seconds without a
successful update. It does not infer charging state.

For manual recovery only, stop `zmalacall-pairing` first to avoid competing agents.
Switch the remote on and hold its rear Bluetooth button for about three seconds
until the white light flashes. In `bluetoothctl`, enable the adapter, run
`scan on`, and use the address advertised as **Microsoft Presenter+** for
`pair`, `trust`, and `connect`. Keep the discovery/agent session open until
pairing finishes, then stop scanning. The advertised address can change when
pairing mode is entered again; use the latest address rather than a saved one.

Moving an SD card to another Pi does not transfer the Bluetooth controller's
identity. Pair the Presenter again with the new board. If `bluetoothctl show`
reports `Powered: no` or `PowerState: off-blocked`, check the radio block and
run `sudo /usr/sbin/rfkill unblock bluetooth`, then `bluetoothctl power on`.
Keep an interactive `bluetoothctl --agent NoInputNoOutput` session open and
select `default-agent` before scanning and pairing; a missing agent can cause
authentication failures. Trust the successfully paired remote so it reconnects.

Back/Next emit Page Up/Page Down, which select contacts. **Mute is the green
call/answer button; Teams is the red cancel/reject/end button.** Hold Pointer
and move the remote up/down to raise/lower the C20 speaker volume. Sideways
motion is ignored. Each 64 units of relative vertical movement changes volume
by two percentage points. A vertical bar at the right shows 0–100% while held and
for two seconds after release; a red exclamation mark indicates mixer failure.
This changes call and ringtone playback, preserving microphone gain and mute.
Local adjustments survive calls and media-engine rebuilds for this app session;
restarting restores the server default, and a changed server volume setting
replaces the local adjustment when the configuration is applied.
The adapter reads only Presenter+ input devices and measured raw reports,
dispatches on Tk's thread and rediscovers devices after a reconnect. Volume
motion is accepted only while Pointer is held on that same raw device; release
or disconnection stops it. Mixer changes are coalesced off the UI thread and
submitted at most ten times per second. The installer grants the input group access to this specific
Bluetooth HID device; it does not grant access to the C20's vendor reports.
Pairing and button reports were verified on the Pi; a full physical four-button
call test is still required.

When the TV is in standby or on another input, the first mapped button press
wakes it and selects the terminal without performing that button's action.
Presses during HDMI settling are also consumed. Once the terminal is visible,
the navigation/call buttons work normally. Pointer volume adjustment does not
wake the TV or switch inputs. Explicit browsing leaves
the TV on the terminal, while incoming calls retain their previous-state
restoration behavior. CEC never changes the TV volume or mute. Screens without CEC
keep normal button behavior; TVs that do not report routing cannot always be
distinguished from an unknown input.

On the Pi, an injected green key changed the reported route from the TV's own
source (`0.0.0.0`) to HDMI 2 (`2.0.0.0`) while the terminal stayed on Home.
The next green key opened confirmation; red cancelled it without further CEC
wake/source commands. These checks exercised the live application and routing
observer, rather than physically pressing the Presenter+ buttons.

### Live configuration

Terminals ask for presence/callback updates using the cached configuration
version. The server sends a full configuration after a settings change and
only live fields otherwise; older clients/servers retain full-response support.
Presence and callbacks are transient and no longer rewrite the offline cache
every two seconds. Ringing pulses update existing canvas items, while countdown
labels change once per second. SIP iteration remains scheduled every 20 ms.

Create a separate Terminal account in administration, add its groups, and choose
**POSIX shell (Linux)** or **Bash (Linux)** under the terminal's command shell.
Windows shells continue to work for Windows accounts; a Linux terminal reports
an explicit failure if it receives a Windows-shell console job.

Download the Wi-Fi and server QR PDFs from that account's terminal card. Show the
Wi-Fi QR to its USB webcam, wait for the 10-second success screen, then show the
server QR. This enrolls the Pi under that account. For development on an already
connected Pi, omit `--wifi-mode connect`: `existing-link` validates the existing
network without changing it. Enrollment retains the scanned credentials until reset.

Real Wi-Fi enrollment uses NetworkManager D-Bus and stores an application-owned
connection. The terminal user needs NetworkManager authorization to create,
activate and delete system connections. The kiosk installer supplies a scoped
Polkit rule for its service user; the application itself runs without root.
For source-tree development, a local desktop session commonly provides authorization.
Reset removes only the profile created by ZmalaCall, leaving unrelated network
profiles alone. Actual Wi-Fi switching should be tested at the Pi's screen,
since it can interrupt an SSH session.

Alternatively, save the terminal's downloaded connection JSON as
`zmala_terminal/data/terminal.json`, or pass its path with `--bootstrap`. It must
contain `server_url`, `device_id` and `device_token`, and use the PC's LAN address.
Keep this file private. The Windows local bootstrap remains pointed at localhost.

Use left/right to select, Enter for green, and Escape for red. A keyboard-style
USB button controller uses those same mappings. Direct GPIO wiring is not yet
implemented. The call and callback confirmations, unavailable-contact status,
missed-call counters, ringing animation and missing-video message are shared
with Windows.

The supported Linux configuration is a Nuroum C20 connected to a Pi with the
`bcm2835-codec` H.264 encoder. Camera, microphone, speaker and ringer are
discovered automatically; an absent C20 produces a clear media startup error
instead of selecting HDMI audio or another webcam. Windows retains device
selection from the server. QR preview is unmirrored and uses an
isolated OpenCV/ZBar worker. Linux text uses Pango/Cairo with Noto fonts for
complex scripts and automatic right-to-left shaping.

## Video defaults and historical Pi 3 validation

Linux uses C20 MJPEG capture, Pi hardware H.264 encoding and FFmpeg software
decoding. 720p at 15 fps is the default, with 1500/4000 kbit/s upload/download
budgets. Each terminal can select 10, 15, 20, 25 or 30 fps. Sending budgets
scale with the target rate; receive capacity stays independent of that target. Resolution and audio processing remain server settings and apply when
idle; legacy local video JSON and codec/fps environment switches are retired.
Enable H.264 on phone peers. The embedded `MSOGL` display uses EGL/GLES and the
shared native-window structure. A custom Liblinphone prefix can
be selected with `ZMALA_LINPHONE_PREFIX` and its library paths configured in the
system dynamic loader.

On the test Pi 3 Model B, Debian 13 ARM64 and Liblinphone 5.3.105:

- Shared unit tests and Linux shell/timeout/descendant-cleanup tests pass.
- All 95 language choices render, including both confirmation screens.
- SIP registration with an isolated Windows-hosted server succeeds.
- Configured/unconfigured start/stop scripts reject duplicate profiles and stop
  the selected instance cleanly.
- Generated Wi-Fi and server QR images decode and re-arm; a worker crash leaves
  the terminal open for retry.
- Calls initiated from either the terminal or the Windows peer receive
  audio/video, draw received video inside the terminal window, and return home
  after red.

Historical generic-camera checks used Xvfb/static media or VP8. The supported
C20 path is checked with the actual webcam and HDMI display, receiving a moving
720p test pattern from Windows. Its outgoing 720p camera feed passed a minute
above 14.26 fps, exceeding the requested 10 fps floor. This does not establish
long-term stability, end-to-end latency or acoustic echo quality. See the C20
verification guide for the measured limits and opt-in live tests.

For headless checks, install `./build_tools/linux/install-terminal.sh --testing`:

```sh
python3 -m unittest discover -s zmala_terminal/common/tests -p 'test_*.py'
xvfb-run -a -s '-screen 0 1366x900x24' \
  python3 zmala_terminal/linux/tests/linux_smoke.py --bootstrap /path/to/test-bootstrap.json
```

Use private test accounts for the smoke tests. The test mutates its own contact
view to check layouts and saves screenshots under `zmala_terminal/common/tests/`.

## Historical test deployment — 9 October 2026

This section records the earlier Pi 3 setup and its measurements. It is not the
current Pi 4 installer configuration. For current defaults use the sections above;
for later performance evidence see [Pi hardware video](pi-hardware-video.md).

The Pi at `192.168.1.44` has the kiosk package installed under
`/opt/zmalacall/current`, with persistent state in `/var/lib/zmalacall`, and
is configured with the existing **term2** account. **term1** remains available
for Windows. The server has been restarted with LAN terminal access enabled.
The `term2` command shell is POSIX `sh`; its remote console returned `aarch64`
from the Pi.

As of 9 October 2026, the Pi has a Nuroum C20 providing camera, microphone and
speaker, with a Samsung TV connected to HDMI 2. The server's terminal settings
report `ZmalaMJPEG: /dev/video0` and `ALSA: Nuroum C20 [Unknown]` for both audio
devices. These are selected automatically. Ringing uses the C20 too.
Explicit MJPEG capture enables actual 1280×720 video; the ordinary SDK camera
entry clamps HD to VGA. 720p passed the minimum 10 received fps requirement;
1080p calls remain unreliable. See [hardware verification](pi-hardware-video.md).
The terminal runs full-screen at 1920×1080 on a
minimal Xorg/Openbox session (`:0`), managed by `zmalacall-display` and
`zmalacall-terminal`. Both start at boot. The application runs as `pi3` and uses
`existing-link` Wi-Fi mode for this test deployment. Its Xauthority file is
`/run/zmalacall-display/Xauthority` (private to the Pi user).

To restart the installed terminal over SSH:

```sh
sudo systemctl restart zmalacall-terminal
```

The earlier virtual test display (`:98`) is independent of the terminal; its
PID was recorded in the old source tree's `zmala_terminal/data/headless-display.pid`.
This virtual display is not configured to start at boot and is no longer needed.

Incoming permitted calls use Linux HDMI-CEC to wake the TV and select the Pi's
HDMI input. `v4l-utils` supplies `cec-ctl`; the terminal user needs membership in
the `video` group (configured by the installer). Enable HDMI-CEC on the TV; on
Samsung this is called Anynet+. A DVI connection cannot carry CEC.

The controller reads the adapter's physical address, rather than hard-coding a
port. It sends Image View On to the TV and broadcasts Active Source, repeating
input selection for up to 20 seconds while the call remains active to accommodate standby wake-up.
Input announcements stop once the TV reports on, avoiding repeated HDMI
selection during established calls. Commands run on a background thread with timeouts.
Before waking the TV, the controller remembers its power state and the last
observed CEC source. Ending, declining or cancelling the incoming call cancels
pending wake retries and restores the previous input, then standby if the TV
was off. A TV already on the terminal input remains there. A new incoming call
supersedes an older queued restoration without losing the original baseline.
Standby restoration retries for a bounded period because a TV still waking
may ignore the first command. Those retries stop promptly for another call.
Windows, missing adapters and CEC failures leave call handling operational.

A manual remote reveal keeps a separate browsing lease. **Return to TV** in local
Settings or the server’s General settings selects 30 seconds (default), 1, 2, 5,
10 or 20 minutes, or Never. After ten seconds of inactivity a three-pixel blue bar at the bottom shows
the remaining idle time. Every button press restarts the countdown and hides
the bar for another ten seconds. Calls and held buttons pause it; activity or returning
from a call starts a full interval. Expiry restores the remembered input/power
state on a worker thread. A new press or incoming call supersedes pending
restoration. Unconfirmed settings and reset confirmations are dismissed, never
applied. Manually switching the TV away releases the lease; an app restart
with no captured baseline does not guess a previous input.

The installer enables `zmalacall-cec.service` to observe routing announcements
and publish an atomic, live state cache under `/run/zmalacall-cec/`. Monitoring
requires `CAP_NET_ADMIN` according to the [Linux CEC mode documentation](https://www.kernel.org/doc/html/v4.9/media/uapi/cec/cec-ioc-g-mode.html).
Only this separate observer service receives the capability; it uses a private
network namespace and a read-only system filesystem. The terminal UI remains
unprivileged. The observer asks existing sources to identify themselves when
its initial state is unknown. Unsupported TVs, built-in smart-TV applications
and inputs without CEC announcements may remain unknown; the terminal then asks
the TV to restore its own previous source without guessing a port. Exact app,
channel, volume and unreported input restoration cannot be inferred from CEC.
For external HDMI sources, the controller also reannounces the remembered source
as a compatibility fallback. It avoids announcing the TV's own `0.0.0.0`
address from the Pi: on Samsung this can report a restored TV route while the
physical screen still displays HDMI. Releasing an active source clears the
observer's cached route until a new source identifies itself. Restoration of
the built-in tuner remains best-effort with CEC alone. A paired Samsung network
remote can return to live TV on models that ignore CEC source release (see below).
Power replies that remain in transition are handled as the destination
state only when there is no stronger remembered power state. A recent Standby
command or settled power report takes precedence over Samsung's sometimes
stale `to-on` replies. First-time adapter configuration is also tracked as a
TV change, so cancellation during setup still restores the prior state.

The Samsung QE55Q60CAU acknowledged CEC power queries and reported the Pi on
HDMI 2 (`2.0.0.0`). The earlier LG monitor did not support the tested CEC query.
The Samsung's power replies sometimes remain in transition. The webcam pointed
at the TV confirmed incoming-call wake-up and HDMI 2 selection from both a
black standby screen and another HDMI input. Follow-up calls confirmed return
to the previously selected HDMI input and return to a black screen after a call
that began in standby. See [verification results](server-verification.md).

Call audio and ringtone playback both follow the server's selected Speaker
device. HDMI ringing was confirmed audible during an actual incoming call.
Auto-answer waits for CEC wake-up and a short settling interval before its
configured countdown; the extra TV wait is limited to 30 seconds. Manual
answering and red-button cancellation remain immediate.

### Samsung broadcast and HDMI selection fallback

Some Samsung TVs acknowledge CEC Inactive Source but keep displaying the Pi.
The optional network remote sends `KEY_TV` after source release when the
remembered source is the TV's own `0.0.0.0` address. This returns to the tuner's
last channel. It never sends channel-number, volume or mute keys; CEC continues
to request the terminal's HDMI input and standby first. If the TV
ignores those standby requests and explicitly reports settled **on**, the
paired remote checks power again after authentication, then sends `KEY_POWER`.
Samsung's power key toggles; unknown, transitional or off replies therefore
never trigger it. It does not restore a smart-TV
app: CEC cannot distinguish those apps from the TV's built-in source.

Reserve the TV's IP in the router, enable remote-device access on the TV, and
pair once as the terminal service user (replace `zmala` for an existing install
running under another user):

```sh
sudo -u zmala python3 /opt/zmalacall/current/build_tools/linux/pair-samsung-tv.py 192.168.1.130
```

Approve the ZmalaCall access prompt if shown. The installer supplies
`python3-websocket`; an existing installation needs that package too. Pairing
writes `/var/lib/zmalacall/tv-remote.json` through the release's data symlink,
with mode 600. It contains the TV IP, access token and SHA-256 certificate pin.
Normal operation checks the pinned self-signed TLS certificate before sending
credentials. Pair again if the TV's IP or certificate changes. Deleting this
file disables the fallback. Credentials are runtime data and excluded from Git
and release archives.

The fallback runs in the existing background restoration worker, waits briefly
for the TV to switch, and stops sending keys when a newer call supersedes it.
An unavailable or unpaired TV leaves CEC restoration and call handling intact.

Some models also ignore CEC Active Source while displaying broadcast TV. A
locally verified source command can be bound to the Pi's physical HDMI address
in the same private `tv-remote.json` file, alongside its existing credentials:

```json
"terminal_source": {"address": "1.0.0.0", "key": "KEY_HDMI"}
```

The Pi 4/Samsung installation was physically verified with this binding:
`KEY_HDMI1` was ignored, whereas `KEY_HDMI` selected the terminal. The generic
key is not a universal numbered-input selector; verify it on the actual TV
before configuring it. Moving the cable to a different HDMI address disables
this fallback until its binding is verified again. The app uses it only when
leaving an awake TV's broadcast source, keeps the first press consumed, and
preserves the binding when refreshing the pairing token. Standby wake remains
CEC-based. No source key is guessed for an unconfigured TV.

With the C930e microphone and TV speakers, term1 reported its own speech coming
back from term2. Term2 now uses the optional speech profile to reduce audio CPU
pressure, with a 500 ms echo tail to test coverage of the TV's processing delay.
SDK calibration did not produce a valid delay measurement (its tones
were not audible), so no calibration value was applied and echo cancellation
remains enabled. Echo removal still needs a listening test with this hardware.

## Automatic camera framing

The optional [automatic framing experiment](automatic-framing.md) detects people
locally and gently frames the group at up to 2× zoom. It is controlled per terminal
from the server and currently supports the Pi C20 camera. See that guide for the
optional detector installation, performance measurements and USB testing limits.

## Installation TV-control checks

The kiosk defers SIP/media startup and pauses idle TV restoration while the
post-enrollment wizard runs. CEC and network operations run in a separate worker,
never on the Tk thread. The power test waits three seconds after a standby
report (with a bounded wait for that report); source changes allow three seconds
between commands. CEC acknowledgements alone never mark a check successful:
the user must confirm what appeared on the TV.

`/var/lib/zmalacall/<profile>/tv-check.json` records version, TV EDID hash and
HDMI physical address, attempts/timestamps, whether each test was performed,
user-confirmed passed/failed results, explicit skips and overall completion.
Writes are atomic. A disk-write failure blocks completion and offers retry.
Interrupted tests resume at a prompt rather than repeating power commands.
Changing the TV/HDMI route invalidates old results on the next startup; factory
reset clears them. With no available CEC connection, skipping is also recorded.
A failed/skipped power or input check disables only that automatic feature.
Keep the TV remote available for manual operation.

Samsung recovery explains Anynet+ and Network Control. Discovery uses local
SSDP; the user chooses a TV by name/IP with Left/Right, then grants ZmalaCall
permission on that TV. No TV is selected silently when several are found.
Pairing uses a pinned TLS certificate and private token storage. The temporary
HDMI command is only saved as verified after the user confirms the entire input
round trip. Old Samsung credentials are not used for a newly detected TV.
Menu names vary: IP Remote may be available, and the TV must permit ZmalaCall.
See [Samsung device permission guidance](https://www.samsung.com/us/support/answer/ANS10001896/).

Sony BRAVIA uses the standard CEC path, with no Samsung network commands.
Recovery instructions point to Settings → Channels & Inputs → External inputs
→ BRAVIA Sync settings: enable BRAVIA Sync control and TV auto power on, and
check the BRAVIA Sync device list. Older models may label these Control for
HDMI / HDMI CEC. Device auto power off controls connected devices when the
TV turns off; it is not the TV-wake setting. Menus depend on model/region.
See [Sony’s current BRAVIA Sync guide](https://helpguide.sony.net/tv/musltn1/v1/en-003/contents/TP1001675609.html)
and [older HDMI CEC settings](https://helpguide.sony.net/tv/gusltnr1/v1/en-003/04-07_03.html).
Sony hardware behavior remains unverified: no BRAVIA was available. In
particular, returning to the built-in tuner must pass the user's round-trip
check; standard CEC does not guarantee that every TV will restore it.

Regression tests use mocked TV transports. `tests/tv_setup_ui.py` exercises all
wizard screens at 900×620, 1280×720 and 1920×1080 without issuing TV commands.
