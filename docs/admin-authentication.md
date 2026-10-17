# Administration authentication

Open the server's LAN address and HTTP port in a browser, for example
`http://192.168.1.118:8080/` on this installation. The server PC can also use
`http://127.0.0.1:8080/` or its `data/open-admin.url` shortcut. The shortcut
contains only the URL, not a credential. Use the configured server IP address;
arbitrary hostnames are rejected by the request-origin checks.

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

On Raspberry Pi hardware running Linux, the production server uses
**`/boot/firmware/zmalacall/admin-password.json`** automatically. On Windows and
other Linux machines it uses **`zmala_server/data/admin-password.json`**. Detection
reads the device-tree model; ARM architecture alone does not select the Pi path.
Isolated custom data stores used by tests/setup tools retain their local path.
The Pi server process needs write access to `/boot/firmware/zmalacall`; a write
failure is reported rather than silently using a different password location.

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
the server, for example in PowerShell:

```powershell
$env:ZMALA_TLS_CERT = 'C:\ZmalaCall-private\server-cert.pem'
$env:ZMALA_TLS_KEY = 'C:\ZmalaCall-private\server-key.pem'
$env:ZMALA_HTTPS_PORT = '8443'
& .\build_tools\start-server.ps1 -NoBrowser
```

Restart an already running server to apply these environment variables. The HTTPS
port defaults to 8443 and must differ from the HTTP port. Allow it through the
private-network firewall and open `https://192.168.1.118:8443/`. Keep certificate
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

On a Pi, shut it down before removing the SD card. Windows exposes the FAT boot
partition, where the file appears as **`<drive>:\zmalacall\admin-password.json`**.
Delete it, safely eject the card and boot the Pi to set a new password. Accounts
and settings remain on the Linux partition. Existing local password files are
moved to the Pi boot location at startup and the old copy is removed, so deleting
the boot file does not resurrect a previous password.
