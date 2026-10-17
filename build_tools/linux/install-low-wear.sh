#!/bin/sh
# Swap reconfiguration is deliberately applied at reboot, never via swapoff.
set -eu
task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
test "$(id -u)" -eq 0
dpkg-query -W -f='${Status}\n' rpi-swap | grep -qx 'install ok installed'
task_journal=/etc/systemd/journald.conf.d/zz-zmalacall-low-wear.conf
task_changed=no
cmp -s "$task_dir/low-wear-journal.conf" "$task_journal" || task_changed=yes
install -D -m 644 "$task_dir/low-wear-journal.conf" "$task_journal"
if cmp -s "$task_dir/low-wear-journal.conf" /etc/systemd/journald.conf.d/90-zmalacall-low-wear.conf; then
    rm /etc/systemd/journald.conf.d/90-zmalacall-low-wear.conf
fi
install -D -m 644 "$task_dir/low-wear-swap.conf" /etc/rpi/swap.conf.d/90-zmalacall-low-wear.conf
if [ "$task_changed" = yes ]; then
    systemctl restart systemd-journald.service
fi
echo 'RAM journal configured (64 MiB); RAM-only swap will take effect after reboot.'
