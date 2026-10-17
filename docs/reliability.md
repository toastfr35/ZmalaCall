# Platform scope and recovery

| Component | Windows | Linux |
| --- | --- | --- |
| Server core | Node.js; desktop start/stop scripts | Node.js; Pi installer supplies systemd supervision |
| Portrait converter | PowerShell/System.Drawing | Python 3/Pillow (`python3-pil`) |
| Terminal | Tk/Liblinphone desktop launcher | Documented Pi kiosk/service, Linux media adapters and C20 routing |
| Maintenance shells | Windows PowerShell, PowerShell 7, cmd | sh, bash; selected shell must match the OS |
| Automated acceptance | Server/model, Windows process tests, source checks | CI runs portable suites and Linux process-group tests |
| Hardware acceptance | Requires live camera/audio/display tests | Requires actual supported Pi/C20/TV calls and recovery tests |

An available adapter or passing fixture does not establish hardware acceptance. The serial Nano keypad host adapter remains a delivery item (TERM024). Public-Internet deployment, certificate enrollment and encrypted SIP/RTP are outside the trusted-LAN prototype contract. LAN administration intentionally permits remote first-password setup; see [administration authentication](admin-authentication.md).

## Persistence and command migration

Configuration, callbacks and commands use ordered asynchronous snapshots. At most one snapshot is writing and one latest snapshot is queued per file; newer complete state replaces an unstarted revision, and all affected acknowledgements wait for that commit. This bounds queued serialized state, but JSON serialization still runs on the event loop. Splitting command output into separate records remains a possible measured optimization.

Mutation responses wait for the stores they change. A failed latest snapshot remains retryable at the next commit barrier. The current in-memory mutation may already be visible when its save fails. Atomic rename prevents a partial JSON file; it is neither a transaction across files nor an fsync guarantee against power loss.

An identical device-settings retry retains the revision but still waits for the persistence barrier. Terminal polling and settings responses share revision-rollback validation and stable-cache filtering. Authenticated terminal HTTP requests refuse redirects so bearer credentials cannot follow a changed destination; enroll the actual API URL rather than a redirecting alias.

HTTP and optional HTTPS listeners share one shutdown promise. Either listener's startup failure closes both and stops SIP; signals use the same path. Active HTTP requests drain before the final persistence flush. This is graceful shutdown, not a bounded kill timer; process supervision remains responsible for a stuck native/dependency operation.

`GET /health` is process liveness. `GET /ready` returns 503 while the latest attempted snapshot has a known unresolved write failure, and returns 200 after it commits. It does not actively probe disk space or assert SIP registration or call readiness. Read-only device polling remains available during unrelated console/callback persistence failures.

Console ownership now follows the immutable physical device serial. Reusing a username or converting a terminal to a phone cannot transfer commands or results. Pending legacy jobs lacking a trustworthy serial are conservatively cancelled/lost on load; their output is not exposed to the current username. Existing legacy history remains in the private bounded snapshot until normal retention removes it. Administrators must explicitly submit any still-needed command after verifying its original execution outcome. A lost command is never automatically replayed.

Output is capped at 65,536 combined UTF-8 bytes after decoding. JSON result bodies allow 400,000 bytes, accommodating escaped control characters. Permanent rejection attempts a small diagnostic and then permits further polling; transient errors retry the same result and lease.

## Terminal recovery

The reported configuration revision advances only after native engine setup succeeds. On failure the failed engine is released, the newest desired configuration remains pending, and idle recovery retries after five seconds. C20 mixer commands run on one worker with latest-value coalescing. Native SDK operations remain on their owning thread; native/QR shutdown waits still require hardware latency testing.

Factory reset immediately removes enrollment secrets and saves only the owned Wi-Fi profile identifiers as a cleanup record. Cleanup retries across failure and restart before accepting another Wi-Fi enrollment. Only successful cleanup removes the record. Existing-link test mode has no owned operating-system profile to delete.

New Linux Wi-Fi enrollments disable power saving in their own NetworkManager profile. On the tested Pi 3B, one 720p call improved after disabling it, but subsequent calls still exposed latency spikes and C20 USB capture failures; this setting is not a complete reliability fix. This is the documented unsigned `powersave=2` setting ([NetworkManager reference](https://networkmanager.dev/docs/api/latest/settings-802-11-wireless.html)). Existing profiles are not silently changed during upgrades. On a dedicated terminal, apply `sudo nmcli connection modify uuid <connection-uuid> 802-11-wireless.powersave 2`; it takes effect on the next activation. For an immediate test without disconnecting the terminal, use `sudo iw dev wlan0 set power_save off`. Revert the profile to `0` to restore the global default.

Portraits download on one independent worker with at most 40 queued paths, a 2 MiB response cap, validation and atomic publication. Failed paths have a one-minute retry delay. Server upload admission is capped at ten outstanding requests and two converter processes; identical in-flight inputs share conversion. Inputs are limited to 16 megapixels and 8192 pixels per side before conversion, and outputs to 480 pixels per side. Cache/log garbage collection still needs a retention policy.

SDP updates for connected calls remain staged until successful negotiation. Rejection leaves established media intact; an accepted disabled stream releases its ports. In-dialog INVITE requires an SDP offer (488 otherwise), and overlapping negotiations receive 491. BUNDLE/ICE remain unsupported. Late responses and socket allocations cannot revive a closed dialog.

## Backup and restore procedure

Stop the server before copying its private data directory and separately stored admin password file. Keep backups access-restricted: they contain device tokens, SIP credentials, command results and possibly SMTP credentials. Back up terminal enrollment/cache only if restoring that same physical device. Do not include runtime data in release packages.

Restore a mutually consistent server snapshot while stopped, start the service, check `/health` and `/ready`, and then verify registration and a real call. If the restored configuration version is older than a terminal's cached revision, the terminal deliberately rejects it. Use the existing factory-reset/re-enrollment workflow with the intended device credentials; do not disable rollback detection or edit credentials to force a match. A server restore epoch and transactional cross-file recovery remain future work.

Linux installers use separate release directories, a current symlink, package checksums and post-start/reboot verification. The server installer restores the previous application release after an upgrade startup failure; this does not roll back dependency, configuration or data changes. A general transactional rollback/restore workflow and managed remote updates remain outstanding. Hardware gates include network loss, camera/audio unplug/replug, repeated calls after idle, connected-peer loss, button usability at TV distance, RTL/long names, CPU/temperature and resource growth.
