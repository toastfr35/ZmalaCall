"""Create a private X11 cookie before the supervised physical display starts."""
import os
from pathlib import Path
import pwd
import secrets
import subprocess


def main():
    user = pwd.getpwnam(os.environ['ZMALA_USER'])
    cookie = Path('/run/zmalacall-display/Xauthority')
    cookie.touch(mode=0o600)
    cookie.chmod(0o600)
    subprocess.run(['xauth', '-f', str(cookie), 'add', ':0', '.', secrets.token_hex(16)],
                   check=True)
    os.chown(cookie, user.pw_uid, user.pw_gid)


if __name__ == '__main__':
    main()
