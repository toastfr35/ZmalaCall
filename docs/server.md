# ZmalaCall server implementation

This guide describes the Linux server's deployment, request boundaries, identities,
SIP/media lifecycle and persistence. It is intended for developers and maintainers.
The Windows executable is a deployment client, not a Windows server runtime.
For user-facing installation and account setup, use `ZmalaServer-Installation.pdf`
and `ZmalaServer-Guide.pdf` beside the release installer. Their retained Word
source is `server_prep.docx`; terminal setup uses `terminal_config.docx`.
Network and build conventions are in
[general.md](general.md); client behavior is in [terminal.md](terminal.md).

The [three-network Docker lab](general.md#three-network-docker-lab) exercises this
server with two native terminal call engines behind separate NAT gateways. It
uses disposable state and never connects to the installed server or terminals.

Contents: [purpose and functions](#server-purpose-and-functions),
[deployment](#deployment-pipeline), [service and SSH](#service-ssh-and-storage),
[authentication](#administration-and-authentication), [account model](#accounts-groups-and-terminal-settings),
[SIP/media](#sip-and-media-internals), [persistence](#persistence-and-backup),
[source map](#source-map-and-verification).

## Server purpose and functions

The ZmalaCall server connects a family's Pi terminals and ZmalaPhone Android apps.
It runs independently on a Raspberry Pi. It holds the shared directory, controls
communication permissions and supplies settings to each terminal. Terminals own
their cameras, microphones, speakers, displays and remote controls.

An administrator uses a web browser to manage the server. Terminal users make
calls and change the permitted local settings through their terminals. The server
connects these two views of the same configuration and reports conflicts.

This description covers the installed Linux server and its host policies. It
excludes installer executables, release packaging and SD-card preparation. Client
behavior appears only where it defines an interface with the server.

### 1. Startup and shutdown

The server starts as a supervised service without a terminal application. It loads
saved state, completes pending restore recovery and opens its network services.
It provides separate process-liveness and persistence-readiness responses.

Shutdown closes listeners and call resources and waits for accepted work and
state writes. Startup failures produce an error instead of leaving a partially
started service available.

### 2. Administration and access control

The first administrator sets a shared password. Later administration requires a
valid session. Password replacement ends existing sessions, and sign-out ends the
selected session. Password hashes and session credentials remain private.

Administration is restricted to loopback or the receiving interface's private local
subnet. Internet clients cannot load the admin pages, sign in, or use a saved admin
session. Authenticated device APIs remain reachable for remote calls.
`http/admin-network.js` compares the TCP peer to the private subnet of the
receiving interface reported by the operating system. It supports IPv4, mapped
IPv4, IPv6 ULA and IPv6 link-local addresses. Unknown interfaces fail closed;
`Forwarded` and `X-Forwarded-For` do not grant access. Keep public traffic directly
forwarded to this listener: a reverse proxy that replaces the source with a LAN
address would need its own equivalent administration restriction.
The server separates administrator sessions, terminal device tokens and SIP account
credentials. Each credential grants only its intended access. Browser requests
also pass address and origin checks. Optional HTTPS protects administration traffic.

### 3. Accounts, groups and portraits

The administrator creates phone and terminal accounts with names, pictures and
contact addresses. Shared groups determine who can communicate. Membership through
a third person does not grant permission.

The server derives contact lists from account data and group membership. A physical
terminal keeps its device identity when it moves between accounts. Account edits
update dependent records, and changes that would disrupt an active call are blocked.
Picture processing limits input size and concurrent work.

### 4. Terminal configuration

The server stores each terminal's language, call, media and presentation settings.
It checks each proposed change before it changes the accepted configuration.
Terminal users can change only the local subset exposed by their Settings page.

Browser editors retain the revision they opened. Account creation checks this
revision too; a stale new-account form receives the same conflict as an edit. Local terminal edits compare the
affected previous values. A conflicting edit produces a visible error. Device
configuration includes that device's credentials but excludes other accounts' secrets.

### 5. Terminal enrollment

The administrator downloads printable Wi-Fi and server QR codes. The Wi-Fi code
contains connection details. The server code identifies the selected terminal and
supplies its device credential. The server does not retain submitted Wi-Fi passwords.

These documents support camera-based setup without a preassigned identity on the
Pi. A separate authenticated bootstrap interface supports existing development clients.

### 6. Registration and availability

SIP clients register their current contact and network flow. The server checks
that the authenticated account matches the registration identity. It checks
reachability on that flow and removes expired registrations.

A saved registration alone does not guarantee that a client is reachable. Terminal
polls receive current availability even when the configuration revision is unchanged.

### 7. Call control

The server authenticates callers and checks group permission, destination availability
and account occupancy. Each account can participate in one current call.
Authorized calls pass through the server to the destination client.

The server correlates answers, cancellation, termination and media changes with the
owning call and network flow. It releases failed or expired calls. Forwarded calls
to a terminal include a proof that the terminal can verify.

### 8. Audio and video relay

The server provides separate packet paths for each participant's audio, video and
control traffic. It forwards encoded media without decoding, recording or changing
the video quality. The clients select their capture and codec settings.

Media destinations come from the authenticated call peers. Negotiation changes take
effect only after acceptance. A rejected change leaves the established path active.
Closing a call releases its ports, including allocations that finish late.

### 9. Phone text notifications

A permitted phone can send a text notification to a reachable terminal. The
server checks sender identity, content type and size, and supplies a verifiable
sender proof. It does not queue text for an unavailable terminal.

The terminal decides how to present the notification. Server activity records
identify the event without retaining the message body.

### 10. Callback requests and reminders

An enrolled terminal or app can request a callback from a permitted contact. Repeated requests
share one pending record. The requester or administrator can cancel it. A connected
call completes requests between the two accounts.

Terminals obtain requests through polling. ZmalaPhone uses signed Firebase hints
and authenticated state refresh to show callback reminders; reachable SIP clients
can also receive SIP notices.
Optional email reminders use the configured deadline and recipient addresses.
Delivery attempts stop when the request is no longer eligible. Acceptance by a
phone or mail server does not prove that a person read the notice.

### 11. Maintenance and diagnostics

The administrator can queue a command for a specific terminal. The server permits
one active command lease per device and records its bounded result. An uncertain
execution becomes lost; the server does not automatically execute it again.

The administration pages show current calls, registrations, terminal reports and
recent events. Device reports remain distinct from server-observed SIP reachability.
The server records when it received a report. The selected Terminals card shows
remote connection/input state, battery percentage and charger connection, plus
C20 connection/recovery state and confirmed USB power. Older or unsupported fields
show unknown; after 20 seconds without a fresh report, peripheral badges show
status unavailable. Live badge updates preserve unsaved terminal settings.

### 12. Saved state

The server retains configuration, callback records and command history across restarts.
Supported migrations preserve identities and credentials. Ordinary saves replace
complete files and limit queued writes.

A successful mutation response waits for its required writes. A failed write
produces an error and affects readiness. Ordinary saves are independent per-file
operations; they do not provide the restore transaction's recovery guarantees.

### 13. Backup and restore

An authenticated administrator can export application data and check a backup
before replacement. Backups include credentials and are sensitive private files.
Operating-system configuration and active network sessions are outside the backup.

Restore requires confirmation and an idle service. It stages the old and replacement
data, then restarts. Startup completes the replacement or restores the previous
data before serving requests. The local network address and ports remain local.
Saved commands do not execute again because of a restore.

### 14. Administration interface

The English web interface supports phone and desktop layouts. It provides separate
pages for overview, accounts, groups, terminals, callbacks and activity. Editors
retain user input until an accepted save or cancellation.

The interface reports validation, conflict and connection failures near the affected
action. Background refresh preserves the active edit and keyboard focus. Sensitive
downloads and credential copying provide explicit feedback.

### 15. Host access and storage

The installed server runs with a dedicated unprivileged account. SSH ingress is
restricted to the physical Ethernet interface. Authenticated administration can
enable or disable wired SSH without stopping the call service.

Routine logs and temporary work use RAM-backed storage to reduce microSD writes.
Application data remains persistent. These policies reduce routine writes; they
do not guarantee recovery from every power or storage failure.

### Qualities that apply to all functions

The server checks external data before use, bounds retained work and isolates
late results from newer operations. It keeps durable configuration separate from
short-lived availability and session state. Errors do not become success messages.
Functional tests and measured code coverage provide distinct evidence; neither
alone proves call quality or hardware compatibility.

## Deployment pipeline

`build_tools/server_installer/` provides the Tk GUI and headless entry point.
It shares `windows_installer/ssh_transport.py` and the read-only target probe with
the terminal installer. Transport owns host-key pinning, bounded SSH commands,
reconnection and durable job monitoring; each product owns its package, host
validation and post-reboot checks. Server readiness uses `check-server.py`,
not the terminal-specific `check-low-wear.py`. Its accepted target is Raspberry
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
$setup = Start-Process .\ZmalaServer-Pi4-setup.exe -Wait -PassThru -ArgumentList `
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

GitHub's **Publish release** workflow builds the same executable without private deployment
data. Each release provides the server Installation and Guide PDFs alongside the
installer, together with the terminal and Android assets. Word sources stay in
the repository and are excluded from the embedded Pi package. Generate a local
Linux source archive separately with
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
Administration requires the server's local network on both HTTP and HTTPS.
With HTTPS configured, non-loopback HTTP administration is also rejected;
authenticated terminal HTTP traffic remains available only outside secure relay mode.
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

Accounts have exactly one type: **App** or **Terminal**. Schema 7 migrates legacy `linphone` accounts to `app`, preserving their SIP credentials and adding independent app enrollment. Type conversion replaces the device ID, token and SIP password; personal details and groups remain. Terminal enrollment has a stable device ID
and token distinct from SIP identity. On Terminals, associating a device with an
occupied terminal account swaps device associations: serial, token, device
settings and console history follow the device; SIP credentials, names, pictures
and groups stay with accounts. Both accounts are checked for active calls.
Renaming preserves linked records while changing the SIP address. Active calls
also block credential/type changes and account deletion.

Terminal selectors show the account name first and retain the full hardware serial in
Account association. Cards separate Connection, Remote & camera and enabled Call features
status from the settings. Terminal cards group Calls, Video & audio and General settings.
A sticky Save changes bar shows Unsaved settings for a modified settings form;
association changes remain a separate submission. **Setup** downloads
Wi-Fi/server QR PDFs; **Console** selects the maintenance shell. These QR PDFs
are runtime provisioning documents, separate from project documentation. App setup
sheets include a clickable latest-release APK link, installation instructions and
the private enrollment QR. Display the QR on another screen, print it, or use the
app's QR-image import.
Settings include auto-answer, fixed C20 hardware information, resolution, FPS, framing,
volume, ringtone, language, portrait count and TV return. See the
[terminal settings implementation](terminal.md#settings-and-controls) for input and save semantics.

The Ringtone selector defaults to Nokia and offers an audio preview on the
administrator's computer. Add ringtones imports audio files into a private server
library, preserving other unsaved terminal edits. The browser accepts files up to
12 MB, converts their first 30 seconds to mono 16-bit PCM at 16 kHz, and submits
the bounded WAV with the form's configuration revision. The server validates
exact headers, duration and SHA-256 identity, then durably publishes the file
under `data/ringtones/`. At most 64 additional sounds and 40 MiB are retained.
Select a tone and Save changes to assign it; importing alone does not change
other terminals. Only import recordings you have permission to use.

`POST /api/ringtones` is LAN-administrator-only. `GET /api/ringtones/:id.wav`
requires an administrator session or terminal bearer; App and anonymous callers
cannot read the library. Names are bounded, paths are canonical, and conflicts
require reopening the form. Previews stop after ten seconds or navigation. The
Pi receives the catalog and caches its selection; Nokia stays bundled, so public
installers and source releases contain no privately imported music.

The Pi terminal settings page has no alternative camera, microphone or speaker
selectors. All three are supplied by the Nuroum C20. Legacy API selector strings
remain validated for compatibility, but the Pi ignores them and browser saves
clear them. A waking C20 is retried automatically; TV audio is never a substitute.


Current editors capture their opening configuration revision and reject stale
saves with HTTP 409. Polling does not rebase drafts. Reopen/review after a conflict.
Revisions are global, so unrelated changes may conflict; older unversioned API
clients retain compatibility without that protection. Photo uploads are scoped
to their editor so a late response cannot save into another account dialog.

### Callback requests and email

Pending requests are unique per requester/recipient pair and require current
group permission. They survive restart, follow username edits and complete when
a call connects in either direction. Cancellation, permission revocation, account
deletion or conversion that invalidates enrollment removes eligibility. Terminal polls
include only that terminal's requests, independently of configuration revision.

Reachable SIP clients receive server-generated MESSAGE notices over their
registration flow. Independently, eligible App accounts receive signed Firebase
state hints, even without a live SIP connection; Android fetches current authorized
callback state before showing a notification. Failed deliveries retry at most
once/minute, with pending work checked every five seconds and on registration.
Terminal recipients use polling and show incoming requests even if the requester
is offline. Neither SIP nor Firebase acceptance proves a person read the reminder.

Callbacks opens on Pending, with separate counts for Pending and History. The selection
survives live refreshes; completed and cancelled records remain in History.
Filtering does not change or remove records. The request list precedes reminder settings.

Callbacks defaults to email after one hour and removal after four hours, both
from creation; fractional hours are supported and removal follows email.
Policy edits apply to pending requests. Expired records are deleted; completed
and cancelled history is capped at 200 on every saved transition, including the
last cancellation or completion. Requester type conversion cancels its pending
requests; ordinary rename preserves them. Accounts accept one-to-ten unique email
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
Factory development state retains the legacy `windows-terminal` serial and PowerShell default.
Pi enrollment selects its POSIX shell; the server accepts legacy desktop shell values
for compatible clients. These labels do not identify the server operating system.

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
survives restart. Account deletion/conversion retires its queued/running work
before acknowledgement; every saved transition caps completed history at 200.
Standalone detached-child cleanup remains an acceptance gap.

## SIP and media internals

Registrations, INVITEs and phone text messages are authenticated; group checks and
terminal-specific proofs protect delivery. Exact-flow OPTIONS probes run every
five seconds with a five-second timeout. Unreachable unexpired registrations are
retained for recovery; late probes cannot alter replacement flows. Clients refresh
presence independently of configuration revision and preflight outgoing calls.

Phone text supports nonempty text/plain or message/cpim up to 16,384 JavaScript UTF-16 code units. This content limit is not a UTF-8 byte limit. The terminal
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
is unsupported in LAN relay mode; secure relay mode retains ICE. Closed dialogs
cannot be revived by pending asynchronous work.

For ZmalaPhone, download the App account server QR and scan it in the app.
`GET /api/app/config` authenticates with that app bearer token, returns only its
identity and permitted contacts, and excludes Pi settings and other account secrets.
App tokens cannot use terminal APIs. The app supports LAN and secure relay calls with Firebase incoming alerts; see [Android implementation](android.md). Legacy SIP clients keep
their migrated credentials; LAN calling uses video, no media encryption and no ICE/STUN. Enable H.264
for Pi calls. Video targets are settings, not delivered-frame guarantees;
the relay does not reduce the terminal's camera/codec workload.

## ZmalaPhone push sender

`app-push.js` uses FCM HTTP v1 with an OAuth JWT scoped to Firebase Messaging.
Concurrent sends share one bounded token refresh. Failed or malformed refreshes
remain retryable; a late rejection of an older token cannot invalidate a newer one.
Install a dedicated service-account key outside the release and server data,
owned by root and readable only by the server service group (0640). The dedicated
`push-sender@YOUR_PROJECT_ID.iam.gserviceaccount.com` account has the Firebase Cloud
Messaging API Admin role. Set `ZMALA_FCM_CREDENTIALS` to its absolute JSON path in
a systemd service drop-in and restart when no call is active. On this Pi the path
is `/etc/zmalacall-server/fcm-sender.json` and the drop-in is
`/etc/systemd/system/zmalacall-server.service.d/firebase.conf`. The key is never
included in an APK, repository, installer or exported application backup. A new
installation needs its own private sender configuration. Without this setting,
push is disabled and foreground SIP remains available. Enable Firebase Cloud
Messaging API in the matching Firebase project; phone and Pi require internet.

`POST /api/app/push` accepts the current App bearer's token or null to revoke it.
The server retains one destination per enrollment in private `app-push.json`,
separate from exported backups. Device replacement/type conversion invalidates
old enrollment bindings; stale registrations expire after 30 days and FCM
UNREGISTERED responses remove their destination. `POST /api/app/call/decline`
cancels only a waiting call addressed to that bearer. Administrators and Terminal
bearers cannot use these App APIs as another device.

`app-calls.js` holds authenticated, permitted INVITEs until fresh registration,
without allocating relay media. Waiting and active calls share the 24-call limit
and one-call-per-participant policy. The wait is bounded to 60 seconds; failure,
CANCEL, recipient decline, revocation and expiry invalidate it. Restore refuses
pending calls. Fresh registration rechecks caller credentials, App enrollment and
current permission before forwarding. Signed high-priority data messages contain
no SIP password or caller display name. Cancellation carries the same enrollment
proof. Live contact availability includes current push-eligible App accounts even
without a live SIP registration; blue means push may work, not guaranteed delivery; green requires a live registration.
After the alert, the app connects through the enrolled server's call transport:
LAN HTTP/SIP/RTP or publicly reachable HTTPS/SIP TLS/TURN TLS with SRTP.

## Persistence and backup

Configuration, callbacks and console history use separate ordered snapshots.
Each file has at most one write in progress and one latest queued snapshot;
acknowledgements await the relevant commit. Failed latest writes retry at the
next barrier. In-memory state may already reflect a failed save. Atomic rename
prevents partial JSON, but provides neither cross-file transactions nor fsync
power-loss durability. Synchronous JSON encoding still runs on the event loop.
Unrelated read-only device polling continues through console/callback save errors.

Overview → **Backup and restore → Manage backups** exports a `.zmala-backup`
file through the authenticated administrator API. It includes accounts, profiles,
groups, device/SIP credentials, SMTP settings/password, the configured administrator
password hash, pictures, private ringtones, callback records and console history. The file is
unencrypted and sensitive: store it privately. Sessions, registrations, logs,
bootstrap caches and OS/SSH/TLS configuration are excluded.

`backups.js` serializes all in-memory records before yielding, then reads immutable
hash-named pictures and referenced private ringtone audio. `backup-format.js` encodes a versioned gzip JSON file map.
SHA-256 checksums detect corruption, not authenticity. Both upload and expanded
JSON are capped at 64 MiB. Only four state files and up to 1,000 permitted portrait
and ringtone files combined are accepted. The decoder checks schemas, field limits,
relationships, picture dimensions/hashes, ringtone catalog/PCM hashes and limits,
and administrator hash syntax. Obsolete portrait and ringtone files are removed
on restore. An unsupported backup
configuration version needs a compatible server release.

`POST /api/server/backup/check` returns a date/count summary. The explicitly
confirmed `POST /api/server/backup/restore` requires
`X-Zmala-Confirm-Restore: replace` and the checked revision in
`X-Zmala-Configuration-Version`. These routes, download and status share the
administrator/session/Host/Origin boundary. One backup operation runs at a time.
Calls, running console jobs, SIP/email/Firebase callback deliveries or overlapping HTTP work cause
a retryable conflict. Maintenance gates HTTP/SIP and callback delivery; state is
flushed before staging the replacement and previous snapshot.

`backup-storage.js` fsyncs temporary files, renames them and syncs directories.
A journal under `data/restore-recovery/` commits the staged transaction. After
the 202 response the service shuts down and exits with code 75; systemd's
on-failure policy restarts it. Startup completes the apply before constructing
the Store or opening listeners. Partial failures switch to a durable rollback
phase; failed recovery stops startup and retains the journal. The private
`restore-recovery/previous.zmala-backup` remains until the next restore. Do not
remove a pending journal during troubleshooting. `restore-result.json` records
success or rollback for the overview after sign-in. Recovery files are excluded
from exports, avoiding recursive backups.

Restore preserves this installation's advertised address and HTTP/SIP ports.
It advances the configuration revision beyond both the current and saved values,
so terminals can accept older settings without re-enrollment when their saved
identities still match. A different server address still requires updating
terminal provisioning. Browser sessions disappear: sign in with the administrator
password from the backup. Queued console jobs become cancelled, running jobs
become lost, and leases are removed; commands never replay. Callback requests
resume normal expiry/delivery rules, so an old snapshot can repeat a reminder
already sent after that snapshot was taken.

A manual filesystem restore bypasses these protections. Prefer the supported UI;
for disaster recovery preserve the entire private data directory and any external
password file while the service is stopped. Check `/health`, `/ready`, sign-in,
terminal configuration/registration and a call after recovery.

HTTP/HTTPS listener failures and process signals share one shutdown operation:
stop new callback deliveries, close listeners and SIP, drain admitted HTTP work
and in-flight callback results, then flush state/bootstrap writes. This is graceful
shutdown, not a bounded kill timer; service supervision handles stuck operations.

## Source map and verification

Paths below are relative to `zmala_server/`.

| Modules | Responsibility |
| --- | --- |
| `validation.js`, `terminal-status.js` | Separate account/configuration validation and bounded device telemetry; receipt times belong to the server |
| `main.js`, `shutdown.js` | Composition, bootstrap publication and coordinated shutdown |
| `http/handler.js`, `responses.js`, `admin-routes.js`, `device-routes.js` | Host/origin/authentication boundary and scoped API operations |
| `store.js`, `contact-directory.js`, `accounts.js`, `terminal-settings.js`, `migrations.js` | Validated configuration, revision-cached phone/terminal directories, identities and migration |
| `json-file.js`, `snapshot-file.js`, `history.js` | Startup/tool persistence, asynchronous snapshots and bounded history |
| `backups.js`, `backup-format.js`, `backup-storage.js`, `http/backup-routes.js` | Validated export, restore transaction and recovery |
| `sip-server.js`, `sip-dialogs.js`, `sip-guards.js`, `sip-transport.js`, `registrations.js`, `sip-messages.js` | SIP admission/lifecycle, ordered dialog/media transactions, shared exact-transport ownership checks, validation, presence and messaging |
| `media.js` | RTP/RTCP ports and transactional SDP updates |
| `callbacks.js`, `callback-*.js`, `console-jobs.js` | Callback/reminder jobs and maintenance leases/results |
| `photos.js`, `portrait-gif.js`, `setup-pdf.js` | Bounded static/GIF inspection, Python/Pillow conversion and PDFKit QR documents |
| `web/admin-*.js`, `web/styles/`, `types/` | Browser controllers/styles and strict shared API/DOM contracts |

Device identity is resolved from the authenticated token, never a supplied ID.
Profile validation constructs a complete candidate before mutation. Unchanged
device-setting retries keep the revision but still await persistence. The browser
model owns loaded snapshots; typed JSON remains a validation boundary, not proof
that arbitrary inputs match the contracts.

Photo conversion admits ten uploads, runs at most two converters, deduplicates
identical in-flight inputs and publishes by content hash. New inputs are square, 480–720 per side; outputs are at most 480 per side.
Historical PNG/JPEG backup inspection retains its original 16-megapixel/8192-side bound.
PDFKit uses built-in fonts. Disk portrait garbage collection remains outstanding.

Run `make test`, `make lint` and `make requirements` as described in
[general.md](general.md#development-tools-and-checks). Unit scenarios under
`tests/server/LLT/` trace directly to server LLRs; HTTP/SIP/system scenarios under
`tests/server/HLT/` trace to server HLRs. Each file starts with its stable test ID,
requirement links, procedure and pass criteria. The generated Tests report shows
remaining HLR gaps separately from planned tests; missing server LLR unit coverage
fails validation. Plans do not claim execution success. `S-LLT-027` runs the
actual admin controllers and CSS in headless Chromium with deterministic API
responses, checking phone/desktop layout and editor-local errors.
Installer readiness checks verify HTTP and both UDP/TCP SIP listeners on all
IPv4 interfaces after reboot, as well as service and low-write storage policy.
For browser changes use
`tests/support/server/http-fixture.js` with disposable data. Check all six pages
at 320, 390, 768, 1024 and 1920 CSS pixels, 700/850 breakpoints and short landscape
height. Check modal scrolling, long names, keyboard focus across polling,
Escape/Enter behavior, plain-LAN-HTTP copying, conflict messages, console reopening
and settings persistence. Viewport tests do not certify physical iOS/Android use.

### Server requirement baseline

The server baseline follows [the rewrite procedure](../howto_rewrite_requirements.md).
Its 15 functional areas contain 31 HLRs and 107 LLRs. HLRs link to product items,
and each LLR links to an HLR in the same area. The text uses short sentences,
active voice and consistent technical terms, following the published
[ASD-STE100 principles](https://www.asd-ste100.org/STE_faq.html). This review is
not a controlled-dictionary compliance certificate.

[The server migration map](../requirements/server/migration.json) records all
replaced items and their successors, including splits. A successor records the
behavior that was carried forward; it does not establish verification. The flat
legacy ID lookup selects a primary successor for older tooling.

All server LLRs have direct LLT plans and implementation anchors; all HLRs have
direct HLT plans. System coverage
is separate: a planned trace does not prove that a scenario passed or that all
conditions in its requirement were tested. The local
[server rewrite report](../tests/coverage/server-rebaseline/index.html) records
execution results, LLT-only coverage, missing system plans and environment limits.
Regenerate published requirements with `make requirements`.

The Linux HLTs now include real UDP Digest-authenticated text delivery, real
portrait conversion through HTTP and Pillow, and a disposable production process
for listener startup, startup failure and SIGTERM persistence. The shutdown
scenario also holds an admitted HTTP request open and checks concurrent stop
requests, draining and media-resource release. These tests do not modify live
accounts or require a deployed terminal.

For installed-host acceptance after reboot, use a prepared checkout on the Pi:
`sudo env ZMALA_INSTALLED_HOST_TESTS=server python3 -m unittest
tests.server.HLT.test_installed_storage -v`. It reads effective journal, swap,
mount and service policy and checks that account/password storage is persistent
and private. It does not print credentials or change the host. Ordinary CI skips
this test explicitly; a process-level pass does not qualify the installed Pi.

The runtime photo converter is `build_tools/convert-photo.py`. The requirement
inventory explicitly includes this helper, so its code and command entrypoint
contribute to server coverage even though the file is outside `zmala_server/`.


## Secure calls when a terminal network blocks UDP

Secure relay mode is an explicit deployment choice for all Terminal and App accounts.
The default remains the existing LAN SIP/UDP relay. Secure mode uses HTTPS for
configuration, SIP over TLS, and endpoint ICE/SRTP through coturn over TLS. It
keeps SIP Digest authentication and signed caller proofs. The signalling server
can read the SDES media keys; this is not end-to-end encryption against the server.
Plain SIP phones must support this secure ICE/SRTP policy to join this deployment.
There is no silent downgrade and no automatic retry of a failed call over plaintext.

Provide three reachable TLS endpoints: configuration, SIP and TURN. SIP and TURN
default to public TCP 443. The original tested topology uses separate public IPs
for these endpoints. Three DNS names
on one IP do not by themselves provide three listeners on port 443. TLS/SNI
multiplexing is not qualified. A normal HTTP reverse proxy cannot proxy SIP or
TURN; use TCP forwarding without terminating SIP/TURN TLS. These connections also
need working DNS and a correct system clock. A firewall that permits only browser
HTTPS through a proxy can still block SIP/TURN on port 443.

For a home server with one public IP and one hostname, use HTTPS on TCP 443,
SIP TLS on TCP 5061 and TURN TLS on TCP 5349. Set `sip_public_port: 5061` and
`turn_public_port: 5349` in the policy below, and set coturn's `tls-listening-port`
to 5349. The defaults remain 443 for existing deployments. Client networks must
allow outbound TCP to the selected ports; a network allowing only port 443 still
needs the original separate-endpoint deployment. Configure the router to forward
443 to the Pi's 8443, 5061 to 5061, 5349 to 5349, and the selected coturn UDP
relay range to the Pi. Reserve the Pi's wired LAN address in DHCP. Port 80 can
be forwarded to an ACME challenge responder for certificate issuance/renewal.
Use the same trusted hostname certificate for all three TLS services. All client
connections are outbound; the phone and terminal routers need no port forwarding.

The server Installation PDF includes a generic router walkthrough for this
single-Pi topology, including DHCP reservation, DDNS, double NAT and CGNAT,
the forwarding rules, and outside-network checks. Its editable source is
`docs/server_prep.docx`; `build_tools/update-network-guides.py` maintains the
network sections. Forwarding is separate from secure-service provisioning and
must match the configured listeners and coturn relay range.

One reference Pi deployment uses a wired DHCP reservation and relay UDP ports
`30000–30199`. A router DDNS updater maintains its public A record. In that deployment, `zmala-turn-address.timer`
checks the A record every five minutes and updates coturn's external-address
mapping and public peer allowlist after an address change. DNS failure leaves
the existing mapping intact. This is site deployment configuration, not part of
an account backup; preserve it when replacing the server. An IP change can
interrupt existing calls while DNS and the relay converge.

Certbot's standalone HTTP challenge owns port 80 only during issuance or renewal.
`certbot.timer` renews the certificate; its `zmala-certificates` deploy hook copies
the renewed chain/key into the server and coturn service directories with group
read access and restarts both listeners. That restart briefly interrupts service,
including any current call. Keys and the TURN signing secret stay private on the
Pi. Inspect `systemctl list-timers`, the Certbot journal and certificate expiry as
part of deployment maintenance. The administration URL is
`https://YOUR_PUBLIC_HOSTNAME/`, accessible only while connected to the server's LAN
(use the actual receiving interface subnet). External requests receive HTTP 403,
including login and requests with valid administrator sessions. Remote phone and
terminal APIs still use the same HTTPS hostname. The previous HTTP administration URL is refused in
secure mode. Existing devices need an HTTPS enrollment address.

On the server, create a private JSON policy file readable by the service account:

```json
{
  "https_url": "https://config.example.org",
  "sip_host": "sip.example.org",
  "sip_listen_port": 5061,
  "sip_cert": "/etc/zmalacall-server/sip-fullchain.pem",
  "sip_key": "/etc/zmalacall-server/sip-key.pem",
  "turn_host": "turn.example.org",
  "turn_realm": "turn.example.org",
  "turn_secret_file": "/etc/zmalacall-server/turn-secret"
}
```

Replace the example names with real DNS names and obtain trusted certificates.
Keep the keys and shared secret out of Git and account exports. Generate the secret
with `openssl rand -hex 32`, store it with mode 0640 and the service group, and use
that same value in coturn's `static-auth-secret`. Add a systemd service override:

```ini
[Service]
Environment=ZMALA_SECURE_CALLS_FILE=/etc/zmalacall-server/secure-calls.json
Environment=ZMALA_TLS_CERT=/etc/zmalacall-server/https-fullchain.pem
Environment=ZMALA_TLS_KEY=/etc/zmalacall-server/https-key.pem
Environment=ZMALA_HTTPS_PORT=8443
```

Forward public configuration TCP 443 to the server's 8443, and public SIP TCP 443
to 5061. The Host check accepts the policy's public HTTPS origin. SIP Via and
Record-Route advertise the public TLS endpoint, not the internal listener port.
Run `systemctl daemon-reload` and restart `zmalacall-server`. Invalid policy or
missing certificates stops startup. HTTP remains available only for health/readiness
checks in secure mode. Use the HTTPS address from the server LAN for administration and print new server
QR codes: existing HTTP enrollment is not automatically changed.

Configure an Internet-reachable coturn host with its own certificate and key:

```ini
tls-listening-port=443
use-auth-secret
static-auth-secret=REPLACE_WITH_THE_PRIVATE_SHARED_SECRET
realm=turn.example.org
fingerprint
no-udp
no-tcp
no-dtls
no-tlsv1
no-tlsv1_1
no-cli
no-multicast-peers
no-tcp-relay
user-quota=8
total-quota=200
min-port=30000
max-port=30199
cert=/etc/turnserver/fullchain.pem
pkey=/etc/turnserver/key.pem
```

Bind the coturn listening/relay IPs explicitly. If that host is behind NAT, set its
`external-ip=PUBLIC/PRIVATE` mapping and forward the configured relay range as well.
Allow TCP 443 from the terminal networks. TURN's server-side UDP relay sockets are
still used; only the terminal-to-relay leg travels over TLS/TCP. Do not enable
`no-udp-relay`. Restrict relay peer addresses with coturn allow/deny lists and host
firewall rules so allocations cannot reach private services, loopback, link-local
or cloud metadata addresses. For this single-relay design, allow its own relay
address/range and deny unrelated destinations. Keep coturn and OpenSSL patched,
monitor allocation quotas, and protect the relay from unauthenticated resource use.
See the [coturn options](https://github.com/coturn/coturn/blob/master/README.turnserver)
and [Liblinphone network API](https://download.linphone.org/releases/docs/liblinphone/5.2/5.3/c/group__network__parameters.html).

The server returns per-account HMAC credentials compatible with coturn REST
authentication. They expire eight hours after the start of the issuing hour and
rotate hourly. Full authenticated configuration responses renew them even without
an account revision change. The shared signing secret is never returned. Revoke
or rotate the server secret to invalidate outstanding credentials; removing an
account alone does not revoke already issued TURN credentials before expiry.
Back up the deployment policy, TLS keys and TURN secret separately from account
backups. Renew certificates and restart the affected listeners before expiry.

Secure mode validates every active SDP media section for ICE credentials and
supported SRTP key sizes, then preserves it. It creates no legacy UDP relay
sockets. LAN mode retains its source-address pinning and SDP rewrite unchanged.
No mixed legacy/secure media gateway or transcoding is implemented.


On 19 October 2026 the LAN administration restriction was deployed to a test Pi server.
S-HLT-033 passed using the OnePlus over cellular data with Wi-Fi disabled:
admin HTML, JavaScript, authentication status/login and the admin API returned
403 even with a valid session and forged forwarding headers. The enrolled app
configuration and health endpoints returned 200. LAN administration returned
200. The phone's starting Wi-Fi setting was restored. The first live attempt
was interrupted by USB disconnection and is not counted as a pass. A subsequent
idle service restart expired the diagnostic sessions, including that interrupted
attempt. The server suite passed 199 tests with four opt-in/hardware skips;
unit policy checks also cover remote app/terminal configuration and portraits.

### App callback requests

App configuration includes `callbacks_enabled: true` and the same per-account
pending `callbacks` view used by terminals. `POST /api/app/callbacks` requires
an App bearer token and a body containing only `to`. It creates the request as
the authenticated account, validates current group permission, flushes the
shared callback store and returns the request in a `callback` object. Existing
pair deduplication, the 400-pending limit, cancellation on permission loss,
expiry and connected-call completion apply to both App and Terminal requesters.
The app receives no access to Pi settings or console APIs. Phone missed-call
counts remain local to the app and are not part of server backups.

App request cancellation uses `DELETE /api/app/callbacks/:id`. Only the authenticated
requesting app can cancel its pending request; the recipient cannot cancel it on
the requester's behalf. The existing callback lifecycle persists the change and
subsequent phone/terminal snapshots remove the pending indicator.

App request cancellation uses `DELETE /api/app/callbacks/:id`. Only the authenticated
requesting app can cancel its pending request; the recipient cannot cancel it on
the requester's behalf. The existing callback lifecycle persists the change and
subsequent phone/terminal snapshots remove the pending indicator.


### Contact presence colours

Contacts distinguish confirmed activity from unconfirmed push delivery: **Available**
(green) means a current SIP registration remains reachable under the server's
five-second checks; **Try calling** (blue) means only push eligibility remains;
**Offline** (red) means neither. Both green and blue permit an attempted call.
A push registration is not proof that the app is installed, online or ready to answer.
The API adds `presence` (`available`, `push`, `offline`) to full, delta and preflight
responses; `online` remains true for both callable states for older clients.
Terminal live information expires after six seconds without a successful refresh,
and cached configurations discard both live fields. Android clears the directory
when a configuration refresh fails. Name buttons show a smaller status line;
terminal cards show the status with a check, question mark or cross. New terminal
labels are translated in English and French, with English fallback elsewhere.

Terminal controls expose independent Call volume (`c20_speaker_volume`), Ringtone volume (`ringtone_volume`) and Button sounds volume (`action_sound_volume`), each 0–100% in 5% steps. New defaults are 50%, 50% and 20%. An older profile without ringtone volume inherits its call default. Existing between-step values display the nearest step and change only when Save changes is accepted. The Pi Settings editors and middle-button call-volume overlay use the same 5% grid. Button taps play only during idle navigation/settings, with no taps during calls, ringing or ringtone previews.

The terminal language selector displays native labels in the shared 16-language catalog order, alphabetized by those labels. Removed legacy language choices migrate to English once without changing enrollment or user identity.

## Callback push for App accounts

`CallbackPush` uses the existing App FCM destination independently of SIP registration.
It sends a signed short-lived `callback` hint containing request/requester/device IDs,
not display text. Android fetches current authorized state before showing an ordinary
reminder. Accepted state fingerprints persist privately in callback records and are
omitted from API views. New requests, cancellation and completion trigger delivery;
the existing five-second callback sweep and token registration resume pending work.
Failures retry no more than once per minute with one in-flight send per request.
Persistence, identity, permission and deadline are rechecked before sending, and a
cancellation racing an accepted send schedules the changed state afterward.
Expired reminders also use Android's timeout. Provider acceptance is not proof of
notification display and never completes a callback. Existing terminal views, SIP
notices and email reminders retain their separate behavior.


### Static and animated account portraits

The account creation/edit dialog accepts PNG/JPEG or GIF and displays its limits.
All new PNG/JPEG/GIF uploads are square, 480–720 pixels per side. PNG/JPEG
are capped at 2 MiB. GIF sources are at most 16 MiB, 2–72 frames and 5 seconds.
Delays are 20–2000 ms; absent/zero delays become 100 ms.
Browser checks include magic bytes, encoded size and decoded first-frame dimensions;
the server independently scans complete GIF blocks before bounded Pillow conversion.
Pillow composites disposal/partial frames and normalizes to a 480 × 480 GIF with
40 timeline slots of 50 ms (two seconds at 20 fps), preserving first/last poses and
omitting repeat metadata. Identical quantized frames may combine; conversion rejects an
output that falls outside frame/byte/timing limits rather than publishing it.
Hash-named authenticated GIF routes use image/gif, private immutable caching and
participate in backup/restore alongside static images (the total backup cap still applies).
Terminal selection controls single playback, regardless of source loop settings.
Android decodes a still first frame. No family media is part of the public source.

Device status accepts optional bounded media snapshots: finite nonnegative transport
measurements, validated resolution pairs and safe integer codec counters. Unknown
fields are omitted; missing measurements remain unavailable. Reports are copied
before publication, and rejected reports preserve the last accepted snapshot.

The contact directory caches stable permissions and contact rows for both phone and
terminal readers within one configuration revision. Returned rows are detached;
presence and callbacks are enriched at the HTTP boundary. Configuration mutations
invalidate all derivations together. Identity-changing administration also rejects
accounts participating in push-wake calls, before those calls own SIP dialogs.
