#!/bin/sh
# Install from the unpacked release. Code is root-owned; state survives upgrades.
set -eu
export DEBIAN_FRONTEND=noninteractive
if [ "$(id -u)" -ne 0 ]; then
    echo 'Run with sudo: sudo sh build_tools/linux/install-kiosk.sh [options]' >&2
    exit 1
fi
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
if [ -z "${ZMALA_INSTALL_LOG:-}" ]; then
    exec python3 "$task_root/build_tools/linux/install-runner.py" "$@"
fi
task_stage='checking installer arguments and prerequisites'
task_finished() {
    task_result=$?
    trap - EXIT
    if [ "$task_result" -ne 0 ]; then
        printf '\nFAILED during: %s (exit %s)\n' "$task_stage" "$task_result" >&2
    fi
    exit "$task_result"
}
trap task_finished EXIT
task_step() {
    task_stage=$1
    printf '\n== %s ==\n' "$task_stage"
}
exec 9>/run/lock/zmalacall-install.lock
flock -n 9 || { echo 'Another ZmalaCall installation is running' >&2; exit 1; }
task_user=zmala
bootstrap=
data_from=
wifi_mode=connect
ssh_interface=eth0
splash=yes
framing=yes
display_mode=1280x720
argon_one=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --user) task_user=${2:?Missing user}; shift 2 ;;
        --bootstrap) bootstrap=${2:?Missing connection JSON}; shift 2 ;;
        --data-from) data_from=${2:?Missing data directory}; shift 2 ;;
        --wifi-mode) wifi_mode=${2:?Missing Wi-Fi mode}; shift 2 ;;
        --ssh-interface) ssh_interface=${2:?Missing Ethernet interface}; shift 2 ;;
        --no-splash) splash=no; shift ;;
        --without-framing) framing=no; shift ;;
        --display-mode) display_mode=${2:?Missing display mode}; shift 2 ;;
        --argon-one) argon_one=1; shift ;;
        --help)
            echo 'sudo ./install.sh [--user zmala] [--ssh-interface eth0] [--display-mode 1280x720|1920x1080|auto] [--no-splash] [--without-framing]'
            echo 'Standard image: hostname, login and password are zmala; --user is optional.'
            echo 'Fresh installation: pair remote, scan Wi-Fi QR, then scan server QR. No terminal ID is assigned here.'
            echo 'Add --argon-one for call-only Argon ONE Pi 4 V2 fan control.'
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done
task_step 'Checking OS, Ethernet, archive and available storage'
if [ "$(dpkg --print-architecture)" != arm64 ] ||
    ! grep -aq '^Raspberry Pi 4 ' /proc/device-tree/model; then
    echo 'This release requires a Raspberry Pi 4 with 64-bit Raspberry Pi OS' >&2; exit 1
fi
if ! grep -Eq '^VERSION_CODENAME="?trixie"?$' /etc/os-release; then
    echo 'Use Raspberry Pi OS Lite 64-bit (Debian 13 Trixie).' >&2; exit 1
fi
if ! mountpoint -q /boot/firmware; then
    echo '/boot/firmware is not mounted; cannot safely update boot files.' >&2; exit 1
fi
python3 - <<'PY'
import shutil
for path, minimum_mb in (('/var', 3072), ('/boot/firmware', 128)):
    free_mb = shutil.disk_usage(path).free // (1024 * 1024)
    if free_mb < minimum_mb:
        raise SystemExit(f'Not enough free space on {path}: {free_mb} MiB available; need {minimum_mb} MiB.')
PY
case "$ssh_interface" in ''|*[!a-zA-Z0-9_-]*) echo 'Invalid SSH interface' >&2; exit 1 ;; esac
if [ ! -e "/sys/class/net/$ssh_interface/device" ] || [ -d "/sys/class/net/$ssh_interface/wireless" ] ||
    [ "$(cat "/sys/class/net/$ssh_interface/operstate")" != up ]; then
    echo 'Connect the physical Ethernet interface before installation' >&2; exit 1
fi
if [ -f "$task_root/SHA256SUMS" ]; then
    (cd "$task_root" && sha256sum --check --quiet SHA256SUMS)
fi
case "$task_user" in ''|*[!a-z0-9_-]*) echo 'Invalid user name' >&2; exit 1 ;; esac
case "$task_user" in [a-z]*) ;; *) echo 'User name must start with a letter' >&2; exit 1 ;; esac
if id "$task_user" >/dev/null 2>&1 && [ "$(id -u "$task_user")" -eq 0 ]; then
    echo 'Terminal must not run as root' >&2; exit 1
fi
case "$wifi_mode" in connect|existing-link) ;; *) echo 'Invalid Wi-Fi mode' >&2; exit 1 ;; esac
case "$display_mode" in 1280x720|1920x1080|auto) ;; *) echo 'Invalid display mode' >&2; exit 1 ;; esac
if [ "$argon_one" -eq 1 ] &&
    { systemctl is-active --quiet argononed.service || systemctl is-enabled --quiet argononed.service 2>/dev/null; }; then
    echo 'Argon vendor daemon is already installed. Resolve the competing fan controller before using --argon-one.' >&2
    exit 1
fi
if [ -n "$bootstrap" ]; then
    python3 - "$bootstrap" <<'PY'
import json, sys
value = json.load(open(sys.argv[1]))
assert all(isinstance(value.get(k), str) and value[k] for k in
           ('server_url', 'device_id', 'device_token')), 'Invalid connection JSON'
PY
fi
if [ -n "$data_from" ] && [ ! -d "$data_from" ]; then
    echo 'Migration data directory does not exist' >&2; exit 1
fi
# @llr TLLR116
task_step 'Downloading and installing dependencies (Internet required)'
apt-get -o APT::Update::Error-Mode=any update
xargs apt-get install -y --no-install-recommends < "$task_root/build_tools/linux/dependencies.txt"
apt-get install -y --no-install-recommends xserver-xorg-core xserver-xorg-input-libinput \
    openbox picom xauth x11-utils x11-xserver-utils polkitd
task_step 'Restricting SSH to Ethernet'
sh "$task_root/build_tools/linux/install-ssh-guard.sh" "$ssh_interface"
task_step 'Reducing SD writes: RAM journal and RAM-only swap'
sh "$task_root/build_tools/linux/install-low-wear.sh"
task_step 'Configuring radios, user permissions and case hardware'
# The stock Lite image may soft-block radios when no Wi-Fi was preconfigured.
# No SSID, password or terminal identity is installed here.
rfkill unblock wifi
nmcli radio wifi on
systemctl enable --now bluetooth.service NetworkManager.service
# msdri3 is a Raspberry Pi OS extension, not a universal Xorg option. Limit
# this workaround to the tested board and a driver that includes that path.
if [ -r /proc/device-tree/model ] && grep -aq '^Raspberry Pi 4 ' /proc/device-tree/model &&
    [ -r /usr/lib/xorg/modules/drivers/modesetting_drv.so ] &&
    grep -aq 'msdri3' /usr/lib/xorg/modules/drivers/modesetting_drv.so; then
    mkdir -p /etc/X11/xorg.conf.d
    install -m 644 "$task_root/build_tools/linux/21-zmalacall-pi4.conf" /etc/X11/xorg.conf.d/
fi
if ! id "$task_user" >/dev/null 2>&1; then
    useradd --system --create-home --home-dir /var/lib/zmalacall-user --shell /usr/sbin/nologin "$task_user"
fi
for group in audio video render input; do
    getent group "$group" >/dev/null || groupadd --system "$group"
    usermod -a -G "$group" "$task_user"
done
if [ "$argon_one" -eq 1 ]; then
    getent group i2c >/dev/null || groupadd --system i2c
    usermod -a -G i2c "$task_user"
    if ! grep -Fqx '# ZmalaCall Argon ONE I2C' /boot/firmware/config.txt; then
        printf '\n[all]\n# ZmalaCall Argon ONE I2C\ndtparam=i2c_arm=on\n' >> /boot/firmware/config.txt
    fi
    printf 'i2c-dev\n' > /etc/modules-load.d/zmala-i2c.conf
    modprobe i2c-dev
fi
mkdir -p /etc/udev/rules.d
install -m 644 "$task_root/build_tools/linux/70-zmalacall-presenter.rules" /etc/udev/rules.d/
udevadm control --reload-rules
udevadm trigger --subsystem-match=hidraw
# @llr TLLR117
mkdir -p /opt/zmalacall/releases /var/lib/zmalacall /etc/zmalacall
chmod 700 /var/lib/zmalacall
if [ -n "$data_from" ]; then
    # Existing installed state wins when upgrading or retrying installation.
    cp -an "$data_from/." /var/lib/zmalacall/
fi
if [ -n "$bootstrap" ]; then
    install -m 600 "$bootstrap" /var/lib/zmalacall/terminal.json
fi
chown -R "$task_user:$(id -gn "$task_user")" /var/lib/zmalacall
task_step 'Preparing the terminal release'
release=$(mktemp -d /opt/zmalacall/releases/install-XXXXXXXX)
chmod 755 "$release"
mkdir -p "$release/build_tools"
cp -a "$task_root/zmala_terminal" "$release/"
cp -a "$task_root/build_tools/linux" "$release/build_tools/"
if [ -e "$release/zmala_terminal/data" ]; then
    echo 'Package unexpectedly contains runtime data; refusing installation' >&2; exit 1
fi
ln -s /var/lib/zmalacall "$release/zmala_terminal/data"
task_step 'Compiling camera and audio plugins'
sh "$release/build_tools/linux/build-media.sh"
if [ "$framing" = yes ]; then
    task_step 'Installing automatic framing runtime and model'
    sh "$release/build_tools/linux/setup-auto-framing.sh"
fi
# Release code stays root-owned; the service user writes only persistent state.
task_step 'Activating release and installing startup services'
chown -R root:root "$release"
chmod -R go-w "$release"
for task_service in zmalacall-terminal zmalacall-cec zmalacall-compositor zmalacall-display zmalacall-pairing; do
    task_load_state=$(systemctl show --value -p LoadState "$task_service.service")
    if [ "$task_load_state" != not-found ]; then
        systemctl stop "$task_service.service"
    fi
done
# Retire the old opt-in media launch paths when upgrading an existing Pi.
# Enrollment, TV pairing and persistent state stay in /var/lib/zmalacall.
rm -f /etc/systemd/system/zmalacall-terminal.service.d/hardware-video.conf \
    /etc/systemd/system/zmalacall-terminal.service.d/camera-h264.conf \
    /etc/systemd/system/zmalacall-terminal.service.d/audio-profile.conf
rm -f /usr/local/bin/zmala-hardware-video /usr/local/bin/zmala-camera-h264 /usr/local/bin/zmala-audio-profile
# Select the completed release only after stopping consumers of the old one.
if [ -L /opt/zmalacall/current ]; then
    ln -sfn "$(readlink /opt/zmalacall/current)" /opt/zmalacall/previous
fi
ln -sfn "$release" /opt/zmalacall/current.new
mv -Tf /opt/zmalacall/current.new /opt/zmalacall/current
printf 'ZMALA_USER=%s\nZMALA_WIFI_MODE=%s\nZMALA_DISPLAY_MODE=%s\nZMALA_ARGON_ONE_FAN=%s\n' "$task_user" "$wifi_mode" "$display_mode" "$argon_one" > /etc/zmalacall/terminal.conf
install -m 644 "$task_root/build_tools/linux/zmalacall-display.service" /etc/systemd/system/
install -m 644 "$task_root/build_tools/linux/zmalacall-pairing.service" /etc/systemd/system/
sed "s/@USER@/$task_user/g" "$task_root/build_tools/linux/zmalacall-terminal.service" \
    > /etc/systemd/system/zmalacall-terminal.service
sed "s/@USER@/$task_user/g" "$task_root/build_tools/linux/zmalacall-cec.service" \
    > /etc/systemd/system/zmalacall-cec.service
sed "s/@USER@/$task_user/g" "$task_root/build_tools/linux/zmalacall-compositor.service" \
    > /etc/systemd/system/zmalacall-compositor.service
# A service has no interactive desktop authorization agent. Allow only this
# terminal user to scan/connect Wi-Fi and persist NetworkManager connections.
mkdir -p /etc/polkit-1/rules.d
cat > /etc/polkit-1/rules.d/49-zmalacall-network.rules <<EOF
polkit.addRule(function(action, subject) {
    var allowed = ["org.freedesktop.NetworkManager.settings.modify.system",
        "org.freedesktop.NetworkManager.network-control",
        "org.freedesktop.NetworkManager.enable-disable-wifi",
        "org.freedesktop.NetworkManager.wifi.scan"];
    if (subject.user == "$task_user" && allowed.indexOf(action.id) >= 0)
        return polkit.Result.YES;
});
EOF
if [ "$splash" = yes ]; then
    task_step 'Installing boot screen and rebuilding boot images'
    theme_changed=no
    for theme_file in zmala.plymouth zmala.script; do
        cmp -s "$task_root/build_tools/linux/$theme_file" "/usr/share/plymouth/themes/zmala/$theme_file" || theme_changed=yes
    done
    cmp -s "$task_root/zmala_terminal/common/assets/boot-family.png" /usr/share/plymouth/themes/zmala/boot-family.png || theme_changed=yes
    mkdir -p /usr/share/plymouth/themes/zmala
    install -m 644 "$task_root/build_tools/linux/zmala.plymouth" "$task_root/build_tools/linux/zmala.script" /usr/share/plymouth/themes/zmala/
    install -m 644 "$task_root/zmala_terminal/common/assets/boot-family.png" /usr/share/plymouth/themes/zmala/boot-family.png
    python3 "$task_root/build_tools/linux/boot-branding.py"
    if [ "$theme_changed" = yes ] || [ "$(plymouth-set-default-theme)" != zmala ]; then
        plymouth-set-default-theme -R zmala
    fi
    # Keep a rescue console available on other VTs, but not on the TV at boot.
    systemctl mask getty@tty1.service
fi
task_step 'Starting and checking terminal services'
systemctl daemon-reload
if systemctl cat display-manager.service >/dev/null 2>&1; then
    systemctl disable --now display-manager.service
fi
# Fresh unit files may not have been loaded into the manager yet.
systemctl reset-failed zmalacall-pairing.service zmalacall-display.service zmalacall-terminal.service 2>/dev/null || true
systemctl enable --now zmalacall-pairing.service zmalacall-display.service zmalacall-cec.service zmalacall-compositor.service zmalacall-terminal.service
sleep 8
task_restart_counts=$(systemctl show --value -p NRestarts zmalacall-pairing zmalacall-display zmalacall-terminal zmalacall-compositor zmalacall-cec)
sleep 5
for task_service in zmalacall-pairing zmalacall-display zmalacall-terminal zmalacall-compositor zmalacall-cec; do
    if ! systemctl is-active --quiet "$task_service"; then
        echo "Installation needs attention: $task_service is not stable. Check journalctl -u $task_service." >&2
        systemctl show "$task_service" -p ActiveState -p SubState -p Result -p ExecMainStatus -p NRestarts >&2 || true
        exit 1
    fi
done
if [ "$task_restart_counts" != "$(systemctl show --value -p NRestarts zmalacall-pairing zmalacall-display zmalacall-terminal zmalacall-compositor zmalacall-cec)" ]; then
    echo 'A terminal service restarted during the health check. Inspect journalctl -u zmalacall-terminal -u zmalacall-display -u zmalacall-compositor -u zmalacall-pairing -u zmalacall-cec.' >&2
    exit 1
fi
for task_service in ssh zmalacall-ssh-guard nftables bluetooth NetworkManager; do
    if ! systemctl is-active --quiet "$task_service"; then
        echo "Required service is not active: $task_service. Check journalctl -u $task_service." >&2
        exit 1
    fi
done
nft list table inet zmala_ssh >/dev/null
printf '\nInstalled. ZmalaCall starts automatically at boot.\n'
printf 'Status: sudo systemctl status zmalacall-terminal\n'
printf 'Reboot to test the boot logo. Pair the remote, then scan the Wi-Fi and server QR codes.\n'
printf 'SSH is available only through %s (IPv4 and IPv6).\n' "$ssh_interface"
