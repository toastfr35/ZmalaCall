# ZmalaCall server implementation

This guide describes the Linux server's deployment, request boundaries, identities,
SIP/media lifecycle and persistence. It is intended for developers and maintainers.
The Windows executable is a deployment client, not a Windows server runtime.
For user-facing installation and account setup, read `server_prep.docx`
and `terminal_config.docx`. Network and build conventions are in
[general.md](general.md); client behavior is in [terminal.md](terminal.md).

Contents: [deployment](#deployment-pipeline), [service and SSH](#service-ssh-and-storage),
[authentication](#administration-and-authentication), [account model](#accounts-groups-and-terminal-settings),
[SIP/media](#sip-and-media-internals), [persistence](#persistence-and-backup),
[source map](#source-map-and-verification).

## Deployment pipeline

`build_tools/server_installer/` provides the Tk GUI and headless entry point.
It reuses the terminal installer's SSH/probe machinery while supplying the server
package, host validation and post-reboot checks. Its accepted target is Raspberry
Pi OS Lite 64-bit Debian 13 Trixie on Pi 3 Model B/B+ or Pi 4 Model B. The factory
host/account defaults are `zmalaserver.local` and `zmalaserver`; the initial login
password matches the account name. These defaults are distinct from the web
administrator password and the migrated SIP/device credentials.

The executable embeds the Python/SSH runtime and public server source. It checks
SSH/sudo access, image identity, Trixie/ARM64, model, hostname, boot mount,
Ethernet and storage before uploading. It pins SSH identity, verifies package
checksums and monitors a separate installation job. Internet access on the Pi
is needed for Debian/npm packages. A lost connection does not necessarily stop
the remote job: retain its reported log path and check its state before retrying.

The service starts automatically as `zmalaserver`. Code is root-owned under
`/opt/zmalacall-server/releases`; `current` selects the release and state lives
under `/var/lib/zmalacall-server`. An upgrade startup failure restores the prior
application release, but does not roll back dependencies, configuration or data.
Ordinary upgrades preserve enrollment and server data.

### Migration and cutover boundaries

The optional data-folder field imports accounts, profiles, groups, credentials,
callback requests, console history and portraits. Logs, old backups and obsolete
shortcuts are excluded; in-flight commands are cancelled rather than replayed.
Migration refuses to overwrite existing Pi server data.

Stop mutations on the source before taking its snapshot. Keep a private backup
and retain the source installation until the replacement passes login, account/
portrait comparison, registration and a two-way call. Stop the old server
application after successful cutover. The installer does not edit terminals:
update their enrolled server URL, including `provisioning.json` where present,
and restart them when the address changes. IDs/tokens remain valid after data
migration; use a new server QR when remote reconfiguration is unavailable.

### Headless installer and local build

```powershell
$setup = Start-Process .\zmala_server_setup.exe -Wait -PassThru -ArgumentList `
    '--headless', '--check-only', '--host', 'zmalaserver.local', '--log', 'check.log'
$setup.ExitCode
```

Replace `--check-only` with `--yes` to install and reboot. Use `--data-dir` with
the private source-data directory for migration. Wait explicitly for this GUI
executable in scripts and inspect its exit code: 0 success, 1 failure, 2 invalid
arguments/missing consent. Both modes save logs. To build from this checkout:

```sh
python -m pip install -r build_tools/windows_installer/requirements.txt
python build_tools/server_installer/build.py
```

GitHub's **Build server installer** workflow builds the same executable without
private deployment data. The download places Word guides beside the executable
and technical Markdown in a `docs/` subdirectory. The Word guides are excluded
from the embedded Pi package. Generate the Linux source archive separately with
`python build_tools/linux/package-server.py`; it includes an `install.sh` wrapper.

## Service, SSH and storage

```sh
sudo systemctl status zmalacall-server
sudo systemctl restart zmalacall-server
sudo journalctl -u zmalacall-server -b
sudo nft list table inet zmala_ssh
```

HTTP, SIP and media listen on all IPv4 interfaces. The installer restricts SSH
to the physical Ethernet interface (`eth0` by default), including IPv6 and
packets addressed to Ethernet but arriving through Wi-Fi. The guard owns only
`inet zmala_ssh`; preserve its nftables include and service dependencies.

Overview → **Wired SSH** enables/disables SSH across reboots without stopping
HTTP/SIP. Installation forces SSH on and blocks disabling it while the install
lock is held. Updates require it enabled. Recover locally with
`sudo /usr/local/libexec/zmala-server-ssh on` or through the authenticated web page.

The installer configures volatile journals capped at 64 MiB, RAM-only zram swap,
RAM-backed `/tmp` and `noatime` on the root filesystem. State remains durable;
the filesystem remains writable. Export operational logs before reboot, which
clears them. Installer recovery logs are retained separately.

`GET /health` is liveness. `GET /ready` returns 503 for a known unresolved snapshot
failure and 200 after its commit succeeds. Neither proves registration, call
quality, free disk space or full backup consistency.

## Administration and authentication

Open the server's LAN address/HTTP port; `127.0.0.1:8080` works only on the server
itself. Host/origin checks reject unrecognized addresses. The first visitor sets
a shared 12–256-character password; there is no administrator username or role
hierarchy. First setup is available remotely on the trusted LAN.

**Change password** requires the current password and revokes other sessions.
**Sign out** revokes the current one. Sessions expire after eight hours and on
restart. Cookies are HttpOnly/SameSite=Strict, with Secure added for HTTPS. Login
is limited to five attempts per address/minute and thirty globally/minute.
The server stores a salted scrypt hash and excludes it from API views.

Installed services store the hash in
`/var/lib/zmalacall-server/admin-password.json`, selected by
`ZMALA_ADMIN_PASSWORD_FILE`. A non-Pi Linux source launch defaults to
`zmala_server/data/admin-password.json`; a Pi source launch without the override
uses the legacy `/boot/firmware/zmalacall/admin-password.json`. Check the service
environment before recovery. Damaged password files stop startup rather than
silently reopening setup. Old in-configuration hashes migrate before removal.

Non-browser clients can POST `/api/auth/login` with
`{"password":"...","session_token":true}` and use the returned token as a Bearer
credential. Password changes/logout invalidate those sessions too. Terminal
device tokens remain separate. The old admin token works only before first
password setup. Keep passwords and tokens out of scripts, logs and Git.

### HTTPS

HTTP does not encrypt passwords or sessions. Supply a client-trusted certificate
valid for the server's address with `sudo systemctl edit zmalacall-server`:

```ini
[Service]
Environment=ZMALA_TLS_CERT=/etc/zmalacall/server-cert.pem
Environment=ZMALA_TLS_KEY=/etc/zmalacall/server-key.pem
Environment=ZMALA_HTTPS_PORT=8443
```

Make the key readable only by the service user, reload systemd and restart the
service. Open `https://<server-address>:8443/`; the HTTPS and HTTP ports differ.
With HTTPS configured, remote HTTP administration is rejected, while local
administration and authenticated terminal HTTP traffic remain available.
SIP/RTP remains unencrypted.

### Password recovery

Stop `zmalacall-server`, remove only its configured admin password file, restart,
and immediately set a new password in the browser. This reopens setup to anyone
who can reach the server until the password is set. Do not remove `server.json`
or the data directory. Deleting the file while running takes effect on restart.
Windows access to the SD boot partition can reset only legacy boot-partition
password files, not the dedicated installer's Linux data-partition file.

## Accounts, groups and terminal settings

The responsive English administration has Overview, Accounts, Groups, Terminals,
Callbacks and Activity pages. Accounts owns SIP usernames/passwords, names,
pictures, types and email addresses; Groups owns contact permissions. Two
different accounts can call when they share a group. Membership is symmetric,
not transitive. Contacts are sorted by display name and use account portraits;
terminals do not override those names or ordering.

Accounts can be phones or terminals. Terminal enrollment has a stable device ID
and token distinct from SIP identity. On Terminals, associating a device with an
occupied terminal account swaps device associations: serial, token, device
settings and console history follow the device; SIP credentials, names, pictures
and groups stay with accounts. Both accounts are checked for active calls.
Renaming preserves linked records while changing the SIP address. Active calls
also block credential/type changes and account deletion.

Terminal cards group Calls, Video & audio and General settings. **Setup** downloads
Wi-Fi/server QR PDFs; **Console** selects the maintenance shell. These QR PDFs
are runtime provisioning documents, separate from project documentation.
Settings include auto-answer, camera/audio selection, resolution, FPS, framing,
volume, language, portrait count and TV return. See the
[terminal settings implementation](terminal.md#settings-and-controls) for input and save semantics.

Current editors capture their opening configuration revision and reject stale
saves with HTTP 409. Polling does not rebase drafts. Reopen/review after a conflict.
Revisions are global, so unrelated changes may conflict; older unversioned API
clients retain compatibility without that protection. Photo uploads are scoped
to their editor so a late response cannot save into another account dialog.

### Callback requests and email

Pending requests are unique per requester/recipient pair and require current
group permission. They survive restart, follow username edits and complete when
a call connects in either direction. Cancellation, permission revocation, account
deletion or requester conversion to a phone removes eligibility. Terminal polls
include only that terminal's requests, independently of configuration revision.

Reachable phones receive server-generated SIP MESSAGE notifications over their
registration flow. SIP success means accepted, not read; there is no offline push
service. Failed deliveries retry at most once/minute, with pending work checked
every five seconds and on registration/recovery. Terminal recipients use polling.

Callbacks defaults to email after one hour and removal after four hours, both
from creation; fractional hours are supported and removal follows email.
Policy edits apply to pending requests. Expired records are deleted; completed
and cancelled history is bounded. Accounts accept one-to-ten unique email
addresses; migrated empty lists show a prompt for real addresses.

The Email server dialog configures SMTP transport, sender and credentials.
Blank password edits preserve the existing secret; explicit clearing removes it.
Passwords are omitted from API responses, and device views omit email addresses.
Connection checks do not send mail. The worker sends recipients independently,
persists accepted recipients, retries failures after 60 seconds and rechecks
ownership/expiry/permission around late results. SMTP acceptance immediately
before a crash can still cause duplicate mail; stable message IDs are not an
exactly-once guarantee.

### Remote console

The terminal polls for work every three seconds, runs one command at a time and
reports stdout/stderr/status/exit code under a unique lease. Ownership follows
immutable device identity; a replacement account cannot claim old commands.
Each job retains its selected shell: Windows PowerShell, PowerShell 7 or cmd for
Windows; sh/bash for Linux. Missing/incompatible shells fail explicitly.

Commands run noninteractively as the terminal's session/service user from
`zmala_terminal/`, without automatic elevation or persistent shell state. Default
timeout is 60 seconds, configurable 5–120; combined decoded UTF-8 output is capped
at 65,536 bytes, with a 400,000-byte JSON result limit for escaped text. At most
ten pending jobs are allowed per terminal. Windows Job Objects/Linux process
groups handle cancellation; installed services additionally use cgroup cleanup.

Transient result failures retry the same lease/result, never rerun the command.
Permanent rejection attempts a small diagnostic and permits later jobs. Lost jobs
have an unknown execution outcome and are not replayed automatically. History
survives restart. Standalone detached-child cleanup remains an acceptance gap.

## SIP and media internals

Registrations, INVITEs and phone text messages are authenticated; group checks and
terminal-specific proofs protect delivery. Exact-flow OPTIONS probes run every
five seconds with a five-second timeout. Unreachable unexpired registrations are
retained for recovery; late probes cannot alter replacement flows. Clients refresh
presence independently of configuration revision and preflight outgoing calls.

Phone text supports nonempty text/plain or message/cpim up to 16 KiB. The terminal
validates the server proof and increments a badge without displaying/persisting
the body. Unsupported typing/payload types are rejected; offline delivery returns
480 rather than queueing text. Callback notifications use a separate lifecycle.

The maintained SIP transport patch checks CANCEL peer/tag/CSeq/branch before
transaction caching, then preserves the original INVITE flow when forwarding.
See [patch provenance](../zmala_server/vendor/sip/ZMALA-PATCH.md) before upgrading
the vendored dependency. Late allocations/responses recheck dialog ownership.
SDP updates are staged until negotiation succeeds; rejection preserves active
targets and accepted port-zero streams release sockets. In-dialog INVITE needs
an SDP offer (488 otherwise); overlapping negotiations return 491. BUNDLE/ICE
is unsupported. Closed dialogs cannot be revived by pending asynchronous work.

For a LAN phone client use the reachable server, shared SIP domain, its account
credentials, video enabled, no media encryption and no ICE/STUN. Enable H.264
for Pi calls. Video targets are settings, not delivered-frame guarantees;
the relay does not reduce the terminal's camera/codec workload.

## Persistence and backup

Configuration, callbacks and console history use separate ordered snapshots.
Each file has at most one write in progress and one latest queued snapshot;
acknowledgements await the relevant commit. Failed latest writes retry at the
next barrier. In-memory state may already reflect a failed save. Atomic rename
prevents partial JSON, but provides neither cross-file transactions nor fsync
power-loss durability. Synchronous JSON encoding still runs on the event loop.
Unrelated read-only device polling continues through console/callback save errors.

Stop the server before copying its private data directory and any separately
configured password file. Backups include SIP/device/admin credentials, command
output and possibly SMTP credentials. Restore mutually consistent files while
stopped; then check `/health`, `/ready`, login, registration and a two-way call.
Restoring an older configuration revision can cause terminals to reject it:
use factory reset/re-enrollment with the intended credentials rather than disabling
rollback protection. Restore epochs and transactional recovery remain backlog work.

HTTP/HTTPS listener failures and process signals share one shutdown operation:
drain requests, stop SIP and flush state/bootstrap writes. This is graceful
shutdown, not a bounded kill timer; service supervision handles stuck operations.

## Source map and verification

Paths below are relative to `zmala_server/`.

| Modules | Responsibility |
| --- | --- |
| `main.js`, `shutdown.js` | Composition, bootstrap publication and coordinated shutdown |
| `http/handler.js`, `responses.js`, `admin-routes.js`, `device-routes.js` | Host/origin/authentication boundary and scoped API operations |
| `store.js`, `accounts.js`, `terminal-settings.js`, `migrations.js` | Validated configuration, identities and migration |
| `json-file.js`, `snapshot-file.js`, `history.js` | Startup/tool persistence, asynchronous snapshots and bounded history |
| `sip-server.js`, `sip-guards.js`, `sip-transport.js`, `registrations.js`, `sip-messages.js` | SIP dialogs, validation, exact-flow presence and messaging |
| `media.js` | RTP/RTCP ports and transactional SDP updates |
| `callbacks.js`, `callback-*.js`, `console-jobs.js` | Callback/reminder jobs and maintenance leases/results |
| `photos.js`, `setup-pdf.js` | Python/Pillow portrait conversion and PDFKit QR documents |
| `web/admin-*.js`, `web/styles/`, `types/` | Browser controllers/styles and strict shared API/DOM contracts |

Device identity is resolved from the authenticated token, never a supplied ID.
Profile validation constructs a complete candidate before mutation. Unchanged
device-setting retries keep the revision but still await persistence. The browser
model owns loaded snapshots; typed JSON remains a validation boundary, not proof
that arbitrary inputs match the contracts.

Photo conversion admits ten uploads, runs at most two converters, deduplicates
identical in-flight inputs and publishes by content hash. Inputs are capped at
16 megapixels/8192 per side before conversion and outputs at 480 per side.
PDFKit uses built-in fonts. Disk portrait garbage collection remains outstanding.

Run `make test`, `make lint` and installer tests as described in
[general.md](general.md#development-tools-and-checks). For browser changes use
`zmala_server/tests/http-fixture.js` with disposable data. Check all six pages
at 320, 390, 768, 1024 and 1920 CSS pixels, 700/850 breakpoints and short landscape
height. Check modal scrolling, long names, keyboard focus across polling,
Escape/Enter behavior, plain-LAN-HTTP copying, conflict messages, console reopening
and settings persistence. Viewport tests do not certify physical iOS/Android use.
