# Single-board computer requirements for the ZmalaCall terminal

## Scope

This document specifies an SBC for the **terminal appliance**: the full-screen user interface, QR setup, camera, microphone, speaker, four physical controls, and one bidirectional video call. The requirements describe the workload and allow the software to be ported to the selected platform.

The Node/SIP server may run elsewhere on the LAN. If it shares the SBC, the complete acceptance test below shall be repeated with the server and its expected number of accounts running on the board.

## Architecture and operating system

The SBC may use either **64-bit ARM (ARMv8-A/AArch64 or newer)** or **x86-64**. There is no algorithmic dependency on x86. Selection should favour an architecture with maintained operating-system, GPU, camera, audio, Wi-Fi, and GPIO drivers.

A 64-bit Linux distribution with long-term security support is the preferred appliance platform. It shall provide:

- a graphical session supported by Python and Tk, or an equivalent UI after porting;
- a native window handle that Liblinphone can use for video rendering;
- working OpenGL ES 3.0 or desktop OpenGL 3.3 acceleration;
- camera and full-duplex audio APIs supported by the chosen Liblinphone build;
- a managed Wi-Fi API capable of adding and removing application-created profiles;
- a userspace GPIO API supported by the board kernel;
- automatic application startup in an interactive full-screen session; and
- unattended security updates or another documented update mechanism.

Windows ARM64 or Windows x86-64 is also acceptable if the board has maintained drivers and the port is built and tested natively for that architecture. Emulation shall not be relied upon to meet production performance targets.

## Required hardware

| Area | Minimum requirement | Recommended target | Reason |
|---|---|---|---|
| CPU | 64-bit ARM or x86-64; 4 cores; sustained 1.8 GHz class performance | Recent 4-core or better processor with SIMD support and ample sustained cooling | The board simultaneously renders the UI, encodes and decodes media, polls the server, and services native devices. Final suitability is determined by the workload test. |
| Media acceleration | Software encode/decode of VGA VP8 and H.264 at the required frame rate, or supported hardware acceleration | Hardware H.264 encode/decode exposed through the selected Liblinphone/media stack | A codec block provides no benefit unless the software build and driver use it. Both enabled codecs must remain usable unless the product requirements change. |
| Memory | 4 GB RAM | 8 GB; 16 GB if the server or other management software shares the board | The terminal also runs the OS, graphical session, native media libraries, image caches, and QR worker. It must operate without sustained swapping. |
| Storage | 32 GB persistent storage | 64 GB or larger eMMC or NVMe | Holds the OS, runtime, logs, call databases, configuration, and update rollback space. Avoid an SD card as the production system disk because the application writes logs, caches, and SQLite databases. |
| Graphics | Hardware-accelerated OpenGL ES 3.0 or desktop OpenGL 3.3; one digital display output | Well-supported GPU, HDMI 2.0, 1920×1080 at 60 Hz | The interface animates scaled images and overlays native incoming video. Software-only rendering is unsuitable for production. |
| Display | At least 900×620 usable pixels | Television or monitor at 1920×1080, 60 Hz | The current window has a 900×620 minimum and is intended to run full screen. Touch is unnecessary because the UI has no clickable controls. |
| Camera | One camera supported by the OS and Liblinphone, capable of VGA video at 30 frames/s | UVC USB camera, 720p or better, with autofocus and good low-light performance | Calls request VGA video. The same camera must resolve printed QR codes reliably during enrollment. QR scanning stops before the call engine starts. |
| Audio input | One full-duplex microphone supported by the OS and Liblinphone | USB conference microphone or combined speakerphone | Speech must remain intelligible at the intended seating distance. |
| Audio output | One supported speaker output with adequate room volume | USB conference speakerphone, or HDMI audio qualified with the target television | Ringing and call audio must be audible without interacting with the OS. A combined device with acoustic echo control is preferred. |
| Network | Wi-Fi supporting 2.4 GHz and WPA2-PSK/AES, with an API the application can configure | Dual-band 2.4/5 GHz 802.11ac or newer Wi-Fi plus Gigabit Ethernet | Camera-based setup provisions Wi-Fi. The present QR format supports open networks and WPA2-PSK/AES. Ethernet may carry calls but does not replace Wi-Fi for the specified onboarding flow. |
| GPIO controls | At least four available digital GPIO inputs with configurable pull resistors and edge detection | Five available inputs: LEFT, RIGHT, GREEN, RED, plus one spare; locking connector and labelled ground | The appliance uses four large momentary buttons. Direct GPIO avoids an additional controller and USB connection. |
| I/O | Connections for camera, audio, display, and service access | Two USB host connections plus a spare, HDMI, Ethernet, and an accessible GPIO header | Separate USB camera and audio connections are typical. The SBC or powered hub must supply their combined peak current. |
| Power and cooling | Regulated supply sized for the SBC and all bus-powered peripherals; cooling that prevents throttling | Manufacturer-rated supply with at least 25% power headroom, heatsink, and temperature-controlled fan where necessary | Video encode/decode and display are continuous workloads. Undervoltage, throttling, or peripheral resets during a call are unacceptable. |

The CPU, memory, and storage figures are selection floors. Driver quality and sustained media performance dominate this workload, so a candidate is accepted only after the production image and peripherals pass the tests below.

## GPIO button interface

The appliance shall have four normally-open, momentary physical buttons:

| Input | UI action |
|---|---|
| LEFT | Select the previous contact |
| RIGHT | Select the next contact |
| GREEN | Confirm, call, or answer |
| RED | Cancel, decline, hang up, or contribute one press to the reset gesture |

Each button shall connect one GPIO input to ground when pressed. Each input shall use a pull-up resistor, either an SoC pull-up qualified across reset and boot or an external **4.7–10 kΩ** resistor to the GPIO I/O rail. The buttons and pull-ups shall use the GPIO voltage specified by the SBC, normally 3.3 V; **5 V shall never be applied to a non-5-V-tolerant GPIO**.

The GPIO design and driver shall meet these requirements:

- expose both press and release state to the terminal application;
- debounce both edges, initially using a 30–50 ms stable interval and tuning it with the production buttons and cable length;
- emit exactly one logical press while a button remains held;
- allow different buttons to be detected independently, without a resistor ladder or shared analogue input;
- choose pins that do not drive boot straps, console UARTs, storage, or other required peripherals;
- remain inactive through reset and boot so no false call, answer, or reset press is delivered;
- discard GPIO events before the UI is ready and clear held-button state after focus/session restart;
- protect external button wiring against electrostatic discharge and electrical transients; and
- use a keyed or locking connector with a ground conductor and strain relief.

Long external cables shall use twisted signal/ground pairs. If testing shows false edges, add suitable input filtering or a Schmitt-trigger buffer rather than increasing software debounce until controls feel slow. A USB HID button encoder remains an acceptable fallback on boards without a stable GPIO userspace interface; it must provide the same four press/release events.

The existing Windows prototype consumes keyboard events. The SBC port shall add a GPIO adapter that converts input edges into the terminal's `left`, `right`, `green`, and `red` actions while preserving held-key suppression and the requirement for ten distinct RED presses during factory reset.

## Network capacity

The current application caps terminal video upload at 1,500 kbit/s and download at 2,000 kbit/s, in addition to audio, SIP, configuration polling, and protocol overhead. The installed connection shall provide at least **5 Mbit/s usable upload and 5 Mbit/s usable download per active terminal**, with margin for Wi-Fi variation and other users.

The Wi-Fi signal at the installed television shall remain stable for the duration of a call. Qualification shall use the real enclosure and final positions of the SBC, antenna, television, camera, and USB devices.

## Software port required for an ARM/Linux SBC

The present prototype packages Windows x64 binaries. The port shall preserve the terminal requirements while replacing its platform-specific integration:

1. Build or package Liblinphone, VP8, H.264, QR decoding, and their dependencies for the target OS and CPU architecture.
2. Replace the `MSOGL`/ANGLE Windows video path and native-window bridge with a supported OpenGL or OpenGL ES renderer for the target graphical session.
3. Rebuild the isolated QR camera worker and preview bridge against the target Liblinphone/media APIs.
4. Replace Windows WLAN calls with the target network manager while retaining profile creation, connection verification, cancellation, and factory-reset deletion.
5. Replace Windows process creation, child-process termination, PowerShell launchers, and maintenance shell selection with target-native service and process management.
6. Implement and test the GPIO adapter described above.
7. Select camera, microphone, speaker, and video devices through their target-platform Liblinphone identifiers.
8. Provide secure boot-time startup, logging, crash recovery, updates, and a way to service the appliance without exposing credentials.
9. Run the platform-independent tests and add target integration tests for display, media, Wi-Fi, GPIO, QR scanning, shutdown, and restart.

Porting should begin on the selected SBC or on hardware using the same SoC and drivers. Desktop ARM compatibility alone does not qualify the board's GPU, codec, camera, audio, or GPIO path.

## Firmware and appliance integration

The SBC shall support unattended power-on after loss of mains power. The operating system shall start the terminal in a full-screen graphical session, keep the display awake, and suppress sleep during calls. Production firmware and drivers shall be obtainable for the chosen OS release.

The enclosure shall provide strain relief and enough ventilation for continuous operation. Controls and external connectors shall not expose mains voltage. A hardware watchdog and battery-backed real-time clock are recommended; the port must integrate them if they are required for automatic recovery or correct time before network synchronization.

## Candidate-board acceptance test

A board is suitable only when the production image, enclosure, and final peripherals pass all of the following:

1. Cold-boot into the terminal in full-screen mode without a shell, desktop prompt, library error, or graphics fallback.
2. Leave the terminal idle for 24 hours while polling continues; it must not exit, sleep, lose controls, leak memory continuously, fill storage, or require intervention.
3. Factory-reset it, scan both setup QR codes, join Wi-Fi, and reach the contact carousel using only the installed controls.
4. Exercise each GPIO button for at least 100 presses, short presses, simultaneous presses, and holds of at least 30 seconds. Verify no missed, duplicate, or false events, including during boot and application restart.
5. Verify two-press call confirmation, hang-up, and the ten-distinct-RED-press reset gesture. A held RED button must count only once.
6. Place and receive bidirectional audio/video calls using VP8 and H.264. Run a continuous 60-minute call while displaying incoming video and sending VGA camera video at 30 frames/s.
7. Confirm intelligible two-way audio, acceptable echo, responsive input, correct video rendering, and no camera, audio, USB, Wi-Fi, GPIO, or display reset.
8. Confirm temperatures remain within rated limits, clocks do not settle into thermal throttling, memory is not exhausted, and the system does not sustain storage swapping.
9. Interrupt and restore Wi-Fi, restart the server, terminate the terminal unexpectedly, and power-cycle the appliance. It shall recover its saved configuration and return automatically to an operable full-screen session without false GPIO actions.
10. Repeat the call at the weakest intended installation signal and while expected household traffic is present. If the SBC hosts the server, repeat the endurance tests with the expected phones registered and administration active.

Record the board revision, SoC, firmware, OS image, kernel, driver and library versions, GPIO pin assignment and bias configuration, camera and audio models, power supply, enclosure, peak temperature, peak memory use, codec CPU use, dropped frames, and observed bandwidth. This becomes the qualified hardware configuration; relevant tests must be repeated after a component, OS, driver, or media-library change.
