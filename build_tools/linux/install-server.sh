#!/bin/sh
# Root-owned releases; durable state is separate from replaceable application code.
set -eu
export DEBIAN_FRONTEND=noninteractive
umask 077
test "$(id -u)" -eq 0 || { echo 'Run the installer with sudo' >&2; exit 1; }
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
task_stage=prerequisites
task_old=
task_switched=no
task_finish() {
    task_result=$?
    trap - EXIT
    if [ "$task_result" -ne 0 ]; then
        echo "FAILED during $task_stage (exit $task_result)" >&2
        if [ "$task_switched" = yes ] && [ -n "$task_old" ]; then
            ln -sfn "$task_old" /opt/zmalacall-server/current
            systemctl restart zmalacall-server || true
            echo 'Previous application release restored; migrated data and OS changes retained.' >&2
        fi
    fi
    exit "$task_result"
}
trap task_finish EXIT
exec 9>/run/lock/zmalacall-server-install.lock
flock -n 9 || { echo 'Another server installation is running' >&2; exit 1; }
task_migration=
if [ "$#" -gt 0 ]; then
    test "$#" -eq 2 && test "$1" = --data-archive || { echo 'Unknown arguments' >&2; exit 1; }
    task_migration=$2
fi
test "$(hostname)" = zmalaserver
test "$(dpkg --print-architecture)" = arm64
grep -aqE '^Raspberry Pi (3|4) Model B' /proc/device-tree/model
grep -qE '^VERSION_CODENAME="?trixie"?$' /etc/os-release
grep -q '^Raspberry Pi reference' /etc/rpi-issue
id zmalaserver >/dev/null
test "$(id -u zmalaserver)" -ne 0
test -e /sys/class/net/eth0/device
test ! -d /sys/class/net/eth0/wireless
test "$(cat /sys/class/net/eth0/operstate)" = up
mountpoint -q /boot/firmware
(cd "$task_root" && sha256sum --check --quiet SHA256SUMS)
python3 -c 'import shutil; assert shutil.disk_usage("/var").free >= 1024**3, "Need 1 GiB free"'
if [ -n "$task_migration" ] && [ -e /var/lib/zmalacall-server/server.json ]; then
    echo 'Refusing to overwrite existing server data. Back it up and migrate explicitly.' >&2
    exit 1
fi
task_stage='installing dependencies'
echo "$task_stage"
apt-get -o APT::Update::Error-Mode=any update
apt-get install -y --no-install-recommends nodejs npm python3 python3-pil nftables avahi-daemon rpi-swap
node -e 'if (Number(process.versions.node.split(".")[0]) < 20) process.exit(1)'
task_stage='preparing application release'
install -d -m 755 /opt/zmalacall-server /opt/zmalacall-server/releases /usr/local/libexec
task_release=$(mktemp -d /opt/zmalacall-server/releases/install-XXXXXXXX)
cp -a "$task_root/zmala_server" "$task_root/build_tools" "$task_release/"
mkdir -p "$task_release/zmala_terminal/common/shared"
cp "$task_root/zmala_terminal/common/shared/terminal-languages.json" "$task_release/zmala_terminal/common/shared/"
npm --prefix "$task_release/zmala_server" ci --omit=dev --ignore-scripts --cache /tmp/zmala-server-npm-cache
node "$task_release/build_tools/build-admin.cjs"
install -d -m 700 -o zmalaserver -g zmalaserver /var/lib/zmalacall-server
if [ -n "$task_migration" ]; then
    task_stage='importing server data'
    python3 - "$task_migration" <<'PY'
import json, pathlib, sys, tarfile
root = pathlib.Path('/var/lib/zmalacall-server')
with tarfile.open(sys.argv[1]) as archive:
    members = archive.getmembers()
    for member in members:
        parts = pathlib.PurePosixPath(member.name).parts
        assert member.isfile() and parts and not member.name.startswith('/') and '..' not in parts, 'Unsafe migration member'
        assert member.size <= 32*1024*1024, 'Oversized migration member'
        assert (len(parts)==1 and (parts[0] in ('server.json', 'admin-password.json', 'callbacks.json', 'console-jobs.json') or parts[0].endswith('-avatar.png'))) or (len(parts)==2 and parts[0]=='photos'), 'Unexpected migration file'
    state = json.load(archive.extractfile('server.json'))
    assert isinstance(state.get('users'), dict) and isinstance(state.get('profiles'), dict), 'Invalid server state'
    if 'admin-password.json' in archive.getnames():
        import re
        credentials = json.load(archive.extractfile('admin-password.json'))
        assert re.fullmatch(r'[a-f0-9]{32}:[a-f0-9]{128}', credentials.get('password_hash', '')), 'Invalid admin credentials'
    archive.extractall(root, members=members, filter='data')
# Do not replay an old queued command after moving to a different server.
jobs = root/'console-jobs.json'
if jobs.exists():
    values = json.loads(jobs.read_text())
    for job in values:
        if job.get('status') in ('queued', 'running'):
            job.update(status='failed', stderr='Cancelled during server migration', exit_code=None)
    jobs.write_text(json.dumps(values))
PY
fi
install -d -m 700 -o zmalaserver -g zmalaserver /var/lib/zmalacall-server/bootstrap
chown -R zmalaserver:zmalaserver /var/lib/zmalacall-server
ln -s /var/lib/zmalacall-server "$task_release/zmala_server/data"
ln -s /var/lib/zmalacall-server/bootstrap "$task_release/zmala_terminal/data"
# Application code stays root-owned and readable by the service.
chmod -R a+rX "$task_release"
task_stage='configuring Ethernet-only SSH and low-write storage'
sh "$task_root/build_tools/linux/install-ssh-guard.sh" eth0
install -m 755 -o root -g root "$task_root/build_tools/linux/server-ssh.py" /usr/local/libexec/zmala-server-ssh
printf '%s\n' 'zmalaserver ALL=(root) NOPASSWD: /usr/local/libexec/zmala-server-ssh on, /usr/local/libexec/zmala-server-ssh off' > /etc/sudoers.d/zmalacall-server-ssh
chmod 440 /etc/sudoers.d/zmalacall-server-ssh
visudo -cf /etc/sudoers.d/zmalacall-server-ssh
# Installation and post-reboot verification require wired SSH to remain on.
/usr/local/libexec/zmala-server-ssh on
sh "$task_root/build_tools/linux/install-low-wear.sh"
task_stage='starting server'
if [ -L /opt/zmalacall-server/current ] && [ -d /opt/zmalacall-server/current ]; then
    task_old=$(readlink -f /opt/zmalacall-server/current)
fi
systemctl stop zmalacall-server.service 2>/dev/null || true
ln -sfn "$task_release" /opt/zmalacall-server/current
task_switched=yes
install -m 644 "$task_root/build_tools/linux/zmalacall-server.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now avahi-daemon zmalacall-server
python3 - <<'PY'
import json, pathlib, time, urllib.request
for attempt in range(30):
    try:
        state = json.loads(pathlib.Path('/var/lib/zmalacall-server/server.json').read_text())
        with urllib.request.urlopen(f"http://127.0.0.1:{state['http_port']}/ready", timeout=2) as response:
            assert json.load(response)['ok'] is True
        break
    except Exception:
        if attempt == 29: raise
        time.sleep(1)
PY
echo 'Server installed. Reboot required to activate RAM-only swap; Windows installer will verify afterward.'
