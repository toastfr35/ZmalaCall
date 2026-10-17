#!/bin/sh
# Experimental opt-in on an already installed Pi 4; standard installer stays unchanged.
set -eu
task_user=${1:-zmala}
id "$task_user" >/dev/null
case "$task_user" in ''|*[!a-z0-9_-]*) exit 1;; esac
task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
apt-get install -y uhubctl psmisc
install -m 755 -o root -g root "$task_dir/usb-power.py" /usr/local/libexec/zmala-usb-power
printf '%s ALL=(root) NOPASSWD: /usr/local/libexec/zmala-usb-power on, /usr/local/libexec/zmala-usb-power off\n' "$task_user" > /etc/sudoers.d/zmalacall-usb-power
chmod 440 /etc/sudoers.d/zmalacall-usb-power
visudo -cf /etc/sudoers.d/zmalacall-usb-power
mkdir -p /etc/systemd/system/zmalacall-terminal.service.d
cat > /etc/systemd/system/zmalacall-terminal.service.d/usb-power.conf <<'EOF'
[Service]
Environment=ZMALA_USB_POWER=1
ExecStopPost=+/usr/local/libexec/zmala-usb-power on
EOF
systemctl daemon-reload
echo 'USB power experiment installed; restart zmalacall-terminal to activate.'
