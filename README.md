<p align="center">
  <img src="zmala_server/assets/zmala-icon.svg" alt="ZmalaCall logo" width="96" height="96">
</p>

<h1 align="center">ZmalaCall</h1>

<p align="center"><strong>Family video calls, on your TV or Android phone.</strong></p>

<p align="center">
  <a href="#get-started">Get started</a> ·
  <a href="https://github.com/toastfr35/ZmalaCall/releases/latest">Releases</a> ·
  <a href="#guides">Guides</a> ·
  <a href="https://github.com/toastfr35/ZmalaCall/issues">Report an issue</a>
</p>

ZmalaCall turns a Raspberry Pi and a television into a video-call terminal.
Choose a familiar face with the remote, confirm the call, and talk on the big
screen. It is designed for people who prefer a few physical buttons to a phone
or computer interface.

The system has three components:

- **ZmalaTerminal:** a Raspberry Pi connected to a TV, camera and remote.
- **ZmalaServer:** a separate Raspberry Pi that connects calls and lets an
  administrator manage accounts, contacts and devices from a web browser.
- **ZmalaPhone:** an Android app for calling family on their phones or TV terminals.

![Terminal home screen with five portrait contacts, Clara selected, and clear online and offline indicators](docs/images/terminal-home.png)

*Screenshots on this page use fictional demo contacts and simulated device status.*

## Built around simple calls

- **Faces instead of numbers.** Browse three or five portraits at a time. See
  who is available, missed calls and pending callback requests.
- **A few physical controls.** Left and right select a contact; green confirms
  or answers; red cancels or ends a call. Hold the middle button and move the
  Presenter+ remote to adjust volume.
- **Video that fills the TV.** See the other person with your own camera in a
  small inset. Optional automatic framing keeps people in view, with a maximum
  2× zoom. Resolution and frame rate can be set for each terminal.
- **Help with the television.** On compatible HDMI-CEC TVs, the terminal can
  wake the screen, select its input and restore the previous TV state after
  calls or a configurable idle period.
- **Guided first use.** Screens help connect the camera, pair and test the
  remote, scan Wi-Fi and server QR codes, and check TV control.
- **Settings for each person.** Choose the language, automatic-answer delay,
  framing, speaker volume, portrait count and return-to-TV timeout.

## Settings without a keyboard

Use the same remote to change settings on the TV. Arrow buttons select an option,
green accepts it, and red cancels the change. Accepted settings are saved back
to the server.

![Terminal settings screen editing the automatic-answer delay, with green Accept and red Cancel controls](docs/images/terminal-settings.png)

## Manage from a phone or computer

The browser interface brings accounts, portraits, contact groups and terminal
settings together. Check device and call status, manage callback requests,
download setup QR codes, and back up or restore server data.
Each account is assigned to either an app or a terminal. Give each device its own
account and setup QR code. Server administration is restricted to the server's
local network.

![Server administration Accounts page showing six fictional contacts, their groups and registration status](docs/images/server-accounts.png)

## Call from an Android phone

Install **ZmalaPhone** and scan the setup QR code supplied by your administrator,
on paper or displayed on another screen. You do not need access to the server's
administration page.

Contacts appear as compact rows with a portrait and name. Tap a green name to
start a video call; gray names are unavailable. During a call, tap the video to
show the microphone, audio output, camera-switch and hangup controls. The app
supports portrait and landscape views, with your camera preview in the corner.

Allow notifications to receive incoming-call alerts while the app is closed or
the phone is asleep. This requires internet access and Firebase push configured
on the server. After using Android's **Force stop**, reopen ZmalaPhone to receive
calls again.

## How it fits together

The **terminal** and **Android app** provide the calling interfaces. The
**server** holds accounts and settings, connects calls and relays their audio
and video. It does not record calls. An administrator uses a web browser for
setup and maintenance.

The default setup uses a trusted local network. With a publicly reachable server
and secure relay configured, phones and terminals can call from different
networks using encrypted connections. Follow the server installation guide to
configure internet access; some restrictive networks may still block calls.

## Get started

### Hardware and software

| Component | Current supported setup |
| --- | --- |
| TV terminal | Raspberry Pi 4 Model B, HDMI TV, Nuroum C20 camera/speakerphone and Microsoft Presenter+ remote |
| Terminal case | Argon ONE Pi 4 V2, with automatic fan integration |
| Server | Raspberry Pi 3 Model B/B+ or Raspberry Pi 4 Model B |
| Pi operating system | Raspberry Pi OS Lite **64-bit**, Debian 13 **Trixie**, for both server and terminal |
| Installation computer | Windows; installers deploy to the Pi over wired Ethernet SSH |
| Android phone | Android 9 or later, 64-bit ARM or x86 processor, camera and microphone; notifications and internet access for incoming alerts |

### Downloads

The [latest public release](https://github.com/toastfr35/ZmalaCall/releases/latest)
contains published installers and instructions. New combined releases use these
download names (older releases may contain only the terminal):

| Product | Installation PDF | User guide PDF | Installer |
| --- | --- | --- | --- |
| ZmalaTerminal | `ZmalaTerminal-Installation.pdf` | `ZmalaTerminal-Guide.pdf` | `ZmalaTerminal-Pi4-setup.exe` |
| ZmalaServer | `ZmalaServer-Installation.pdf` | `ZmalaServer-Guide.pdf` | `ZmalaServer-Pi4-setup.exe` |
| ZmalaPhone | `ZmalaPhone-Installation.pdf` | `ZmalaPhone-Guide.pdf` | `ZmalaPhone.apk` |

Published release downloads do not require a GitHub account. Run the Pi setup
programs on a Windows computer; install the APK directly on your Android phone.
Download the matching PDFs for each product you use.

### From setup to first call

1. **Prepare the server.** Follow the server guide to flash the supported OS,
   connect Ethernet and run the server installer. Open its web page and create
   your accounts and contact groups.
2. **Prepare the terminal.** Follow the terminal guide to flash its SD card,
   connect the TV and accessories, and run the terminal installer.
3. **Complete setup on the TV.** Pair and test the remote, scan the Wi-Fi and
   server QR codes, and complete the TV-control checks. The server QR code
   assigns the terminal identity.
4. **Set up phones.** Create a separate App account for each phone and give its
   user the setup QR code. Install ZmalaPhone, scan the QR and allow camera,
   microphone and notification permissions.
5. **Make a call.** Put the accounts in a shared calling group. Select a contact
   on the TV or tap a green contact name on the phone.

### Guides

Use the PDFs supplied with your release:

| Guide | What it covers |
| --- | --- |
| ZmalaServer Installation | SD card, installation and secure internet access |
| ZmalaServer Guide | Accounts, groups, setup QR codes, backups and maintenance |
| ZmalaTerminal Installation | SD card, physical connections and installation |
| ZmalaTerminal Guide | Enrollment, TV settings, remote controls, calls and everyday help |
| ZmalaPhone Installation | APK installation, QR enrollment and incoming alerts |
| ZmalaPhone Guide | Contacts, calls, camera controls and everyday help |

---

[Developer information](for_developpers.md)
