#!/bin/sh
set -eu
task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
task_interface=${1:?Ethernet interface required}
case "$task_interface" in ''|*[!a-zA-Z0-9_-]*) echo 'Invalid Ethernet interface' >&2; exit 1 ;; esac
if [ ! -e "/sys/class/net/$task_interface/device" ] || [ -d "/sys/class/net/$task_interface/wireless" ]; then
    echo 'SSH interface must be a physical wired interface' >&2; exit 1
fi
mkdir -p /etc/zmalacall /etc/nftables.d /usr/local/libexec
printf '%s\n' "$task_interface" > /etc/zmalacall/ssh-interface
install -m 644 "$task_dir/ssh-guard.py" /usr/local/libexec/zmala-ssh-guard.py
# Apply before changing services. Failure must not silently expose Wi-Fi SSH.
python3 /usr/local/libexec/zmala-ssh-guard.py
include='include "/etc/nftables.d/zmala-ssh.nft"'
if ! grep -Fqx "$include" /etc/nftables.conf; then
    cp -n /etc/nftables.conf /etc/nftables.conf.before-zmala
    printf '\n%s\n' "$include" >> /etc/nftables.conf
fi
install -m 644 "$task_dir/zmalacall-ssh-guard.service" /etc/systemd/system/
# Make dependencies active BEFORE attaching them to a running ssh.service.
# Adding BindsTo an inactive firewall can immediately stop the live SSH daemon.
systemctl daemon-reload
systemctl enable --now nftables.service zmalacall-ssh-guard.service
for task_unit in ssh.service ssh.socket; do
    mkdir -p "/etc/systemd/system/$task_unit.d"
    cat > "/etc/systemd/system/$task_unit.d/zmala-ethernet.conf" <<'EOF'
[Unit]
Requires=zmalacall-ssh-guard.service
After=zmalacall-ssh-guard.service
BindsTo=nftables.service
EOF
done
# Re-evaluate ports on subsequent sshd restarts as well as at boot.
cat >> /etc/systemd/system/ssh.service.d/zmala-ethernet.conf <<'EOF'
[Service]
ExecStartPre=/usr/bin/python3 /usr/local/libexec/zmala-ssh-guard.py
EOF
systemctl daemon-reload
systemctl enable ssh.service
