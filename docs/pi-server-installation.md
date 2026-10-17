# Raspberry Pi server installation

Flash Raspberry Pi OS Lite (64-bit), Debian Trixie, with Raspberry Pi Imager.
Set hostname, username and initial password to `zmalaserver`, and enable SSH
password authentication in the image settings. Connect power and Ethernet.
Pi 3 Model B/B+ and Pi 4 Model B are accepted; no desktop, camera or remote is needed.

Run `zmala_server_setup.exe` on Windows, check `zmalaserver.local`, then confirm
installation. An Ethernet IP address can also be entered. The installer verifies
SSH, administrator access, model, OS, wired connection and free space before
uploading. It pins the SSH identity for subsequent connections, verifies the
package checksum, monitors installation, reboots, and checks the running server.
The executable contains its Python/SSH runtime and public application source;
Internet access on the Pi is needed to install Debian and npm dependencies.

## Existing server data

The optional data-folder field imports current accounts, profiles, groups,
credentials, callback requests, console history and portraits. Logs, obsolete
backups and generated shortcuts are excluded. In-flight console commands are
cancelled during import rather than replayed. Existing Pi server data cannot
be overwritten by a migration; ordinary updates preserve it.

The source server should be quiescent when taking the migration snapshot. Keep
a private backup and retain the source installation until the new server is
verified. Moving to another IP also requires updating each terminal's enrollment
URL (including `provisioning.json` where present) and restarting it. Account IDs
and tokens stay unchanged; a new server QR is needed for devices that cannot be
updated remotely. The installer does not silently edit other terminals.

## Headless executable

```powershell
./zmala_server_setup.exe --headless --check-only --host zmalaserver.local --log check.log
./zmala_server_setup.exe --headless --yes --host zmalaserver.local --log install.log
./zmala_server_setup.exe --headless --yes --data-dir "C:\private\server-data" --log migration.log
```

Use `Start-Process -Wait -PassThru` when the caller needs to wait for this Windows
GUI executable. Exit 0 means success, 1 means failure and 2 means invalid arguments
or missing installation consent. GUI and headless runs save logs. Installation
continues on the Pi if an SSH session briefly drops. On an upgrade startup failure,
the prior application release is restored; dependency/configuration changes and
data changes are not rolled back automatically.

## Operation

- Open `http://zmalaserver.local:8080/` or the Pi's LAN IP address. Existing admin
  credentials are preserved on migration; a fresh server has the normal initial
  password setup. Use a DHCP reservation to keep its advertised SIP address stable.
- `zmalacall-server.service` starts automatically and runs as `zmalaserver`.
  Application code is root-owned under `/opt/zmalacall-server/releases`; state is
  private under `/var/lib/zmalacall-server`.
- HTTP, SIP and media listen on all IPv4 interfaces. The SSH firewall accepts SSH
  only through `eth0`, covering both IPv4 and IPv6.
- Overview → **Wired SSH** turns server SSH on/off and preserves that setting
  across reboots. The switch leaves HTTP/SIP running. Installation forces SSH on;
  disabling it is blocked while the installation job holds its lock.
- Recover disabled SSH locally with `sudo /usr/local/libexec/zmala-server-ssh on`,
  or use the authenticated web page. Updates require SSH to be enabled first.
- Journals are volatile and capped at 64 MiB, swap is RAM-only zram, `/tmp` is
  tmpfs and the root filesystem uses `noatime`. Accounts/settings remain durable.
  Reboot clears operational logs; export logs before reboot when investigating.
- The server admin password hash is in
  `/var/lib/zmalacall-server/admin-password.json`. This dedicated server service
  does not require write access to the boot partition. Back up the data directory
  privately; it contains credentials.

Build on Windows with the requirements from
`build_tools/windows_installer/requirements.txt`, then run
`python build_tools/server_installer/build.py`. GitHub's **Build server installer**
workflow produces the same credential-free executable.

## Verification

The Windows executable was exercised against Raspberry Pi OS Lite 64-bit Trixie
on a Pi 4, including migration, an update, reboot, original-password login,
credential/portrait equality, and Ethernet-only SSH off/on from the web API.
Post-reboot checks confirmed the low-write settings and HTTP/SIP listeners.
A muted Windows-to-Pi call received 1080p video at approximately 15 fps and
decoded audio through the new server. Pi 3 is accepted by preflight but still
needs an equivalent hardware run.
