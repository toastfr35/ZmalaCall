# Pi 4 USB power experiment

This is an opt-in experiment for an already installed Raspberry Pi 4 Model B
with a Nuroum C20 and a power-only remote charging cradle. The regular Windows
installer does not enable it.

The Pi 4 switches its external USB ports together: camera and charger lose
power together. Bluetooth and Wi-Fi remain available. See the
[uhubctl Pi 4 notes](https://github.com/mvp/uhubctl#raspberry-pi-4b).

## Policy

- Turn off after five minutes without camera activity, only when the remote's
  reported battery is strictly above 25%.
- Keep power on during calls, ringing, setup, settings and other active screens.
- Restore power when needed for a call or QR scan, when battery is 25% or less,
  or when battery status is unknown/stale.
- A stalled application heartbeat also restores power. Systemd restores power
  after the terminal exits, including an application crash.
- Refuse to switch off if another USB peripheral is attached or camera/audio
  device handles are still open. Do not use this with USB storage.

The root helper deauthorizes the C20 interfaces before cutting the shared supply.
After wake, the app waits for camera and audio enumeration, refreshes the SDK
device lists on its owning thread, and reapplies speaker volume before ringing.
Hub operations run on a separate worker thread. Failed operations leave or
restore power on and are retried with a delay.

## Enable on an existing installation

Deploy the matching terminal sources and `build_tools/linux` scripts first.
Then run on the Pi:

```sh
sudo sh /opt/zmalacall/current/build_tools/linux/install-usb-power.sh zmala
sudo systemctl restart zmalacall-terminal
```

The helper is root-owned with sudo access restricted to its fixed `on`/`off`
actions. Status is written to RAM at `/run/zmalacall/usb-power.json`; logs are
available through `journalctl -u zmalacall-terminal`.

## Disable

```sh
sudo systemctl stop zmalacall-terminal
sudo /usr/local/libexec/zmala-usb-power on
sudo rm /etc/systemd/system/zmalacall-terminal.service.d/usb-power.conf
sudo systemctl daemon-reload
sudo systemctl start zmalacall-terminal
```

Keep the helper and sudo rule until the application has restarted successfully.
This experiment does not alter network or SSH configuration.

## Validation

Automated tests cover the five-minute and 25% boundaries, stale activity,
device-refresh gating, cancelled answers, attached peripherals, open media
handles and rollback after a failed power-off operation.

Hardware testing uses the zmala Pi and muted calls. USB disappearance and hub
power status verify switching; electrical power consumption has not been
measured. A device plugged into an unpowered port cannot be identified until
power returns, so attaching additional USB equipment requires disabling this
experiment first.

On 17 October 2026, the real five-minute idle interval powered down both hubs
with the remote reporting 100%. An incoming call restored the devices and
received 1920x1080 video at a minimum of 13.8 fps. A subsequent muted call
verified nonzero decoded microphone audio and a minimum of 14.6 fps. The audio
probe records to a temporary file instead of speakers and deletes that file.

An isolated controller test used simulated battery readings with real USB power
switching: 26% permitted shutdown; 25% and unknown restored power. Wake took
7.7–7.8 seconds. Controller shutdown also restored the C20. These tests do not
change the Bluetooth battery reading. Power-up adds roughly eight seconds
before the normal auto-answer countdown can begin.
