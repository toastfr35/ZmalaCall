# Administration authentication

Open the server's LAN address and HTTP port in a browser, for example `http://zmalaserver.local:8080/` for the installed Pi server, or its LAN IP. On the server machine, `http://127.0.0.1:8080/` also works. Use a configured hostname/address; request-origin checks reject unrecognized hosts.

The first visitor sets the shared admin password and confirms it. This one-time
setup works from another computer, without access to the server's desktop.
Passwords must contain 12–256 characters. After setup, every browser signs in
with that password and no username. There are no separate administrator roles.

**Change password** in the sidebar requires the current password and signs out
all other sessions. **Sign out** revokes the current session. Sessions expire
eight hours after login and do not survive a server restart. Browser sessions
use HttpOnly, SameSite=Strict cookies; credentials are not stored in URLs or
browser session storage. HTTPS cookies also use Secure. Login attempts are
limited to five per address per minute and thirty globally per minute.

The server stores a salted scrypt hash, never
the plaintext password. It omits the hash and old admin token from admin API
responses. Terminal device tokens continue to authenticate terminal requests
independently. Existing local maintenance tools can use the legacy admin token
only before the first password is configured; afterwards they need a session.

Password-file location depends on how the server was started:

- The dedicated Pi installer sets `ZMALA_ADMIN_PASSWORD_FILE` to **`/var/lib/zmalacall-server/admin-password.json`** in its service. This is on the Linux data partition, not the FAT boot partition.
- Non-Pi Linux source launches default to **`zmala_server/data/admin-password.json`**.
- A source launch on Pi hardware without that override uses the legacy **`/boot/firmware/zmalacall/admin-password.json`** path. Hardware detection reads the device-tree model; ARM architecture alone is insufficient. Isolated test stores retain their own data path.

Check the service environment before recovery if the installation was customized. A write failure is reported rather than silently changing the password location.

For non-browser clients, POST `/api/auth/login` with JSON
`{"password":"your password","session_token":true}` and use the returned
`session_token` as a Bearer credential. Logout and password changes invalidate
these credentials as well. `build_tools/test-console-live.cjs` reads the password
from `ZMALA_ADMIN_PASSWORD` when password authentication is configured; avoid
putting real passwords in command histories or checked-in scripts.

## Optional HTTPS

The default LAN listener uses HTTP, which does not encrypt passwords or sessions
in transit. Configure HTTPS with a certificate trusted by the client computers
and valid for the server's address. Set both certificate paths before launching
the server. For systemd, use `sudo systemctl edit zmalacall-server`:

```ini
[Service]
Environment=ZMALA_TLS_CERT=/etc/zmalacall/server-cert.pem
Environment=ZMALA_TLS_KEY=/etc/zmalacall/server-key.pem
Environment=ZMALA_HTTPS_PORT=8443
```

Then run `sudo systemctl daemon-reload` and `sudo systemctl restart zmalacall-server`.
Make the key readable by the service user only.

Restart an already running server to apply these environment variables. The HTTPS
port defaults to 8443 and must differ from the HTTP port. Allow it through the
private-network firewall and open `https://<server-address>:8443/`. Keep certificate
keys outside the repository. When HTTPS is configured, remote administration
over HTTP is rejected; local administration and authenticated terminal HTTP
traffic remain available. This listener encrypts administration, not SIP media.

## Forgotten password

Stop the server, delete its password file (using the platform-specific path above), then restart
and immediately set a new password through the browser. This reopens one-time
setup to anyone who can reach the server until the new password is set. Existing
account and terminal settings in `server.json` remain intact. Deleting the file
while running takes effect only after restart; existing in-memory sessions are
revoked by the restart.

Older passwords stored in `server.json` are migrated automatically on startup:
the separate file is written first, then the old property is removed. A damaged
password file stops startup rather than silently allowing password setup.

For the dedicated Pi service, use its authenticated SSH/local console to stop `zmalacall-server`, remove `/var/lib/zmalacall-server/admin-password.json`, then restart the service and set the new password immediately. Do not remove `server.json` or the rest of the data directory.

Only legacy source launches using the boot-partition path support recovery by deleting `<drive>:\zmalacall\admin-password.json` from a Windows-mounted SD card. Shut the Pi down before removing that card. This method does **not** reset the dedicated installer's password. Legacy local hashes are migrated before their old copy is removed, preventing accidental resurrection of an old password.