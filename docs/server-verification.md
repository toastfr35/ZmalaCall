# Server and admin verification

This document includes dated hardware observations. Preserve their original
settings when comparing results; they are not current global limits. Current
video defaults and targets are in [the terminal guide](linux-terminal.md#video-defaults-and-historical-pi-3-validation)
and `zmala_terminal/video_settings.py`.

The server runtime and admin source use two strict `checkJs` configurations.
`make lint` runs both along with ESLint, Ruff, shell/native checks, formatting,
generated asset checks and (on Windows) PowerShell parsing. `make test` runs
the server tests and platform-independent terminal suite.

Verification on 6 October 2026 for the completed type-checking pass:

- 46 server tests passed, including malformed terminal diagnostics and SIP
  shutdown during pending SDP work.
- 63 terminal tests ran successfully; three Linux-only tests were skipped on
  Windows.
- The admin interface was tested in a private HTTP fixture. Overview, accounts,
  groups, terminals, callbacks and activity rendered. Account and group edits,
  terminal resolution and callback deadline changes saved. Console and SMTP
  dialogs opened without browser errors. A nullable terminal dropdown lookup
  found during this check was corrected.
- The live server restarted while idle. The Pi terminal restarted, registered,
  reported fresh diagnostics and completed two 15-second calls from the Windows
  SDK test peer. Webcam video remained decodable throughout both calls at about
  15 fps; decoded-frame notifications continued without a three-second gap.
  Calls ended and the Pi returned to its home screen state.
- The AIRHUG 02 camera, hardware H.264 encoder and HDMI playback device were
  detected. Samsung CEC power queries received replies reporting the TV on and
  the Pi's physical address was `2.0.0.0`. The displayed input and audible
  ringtone were not visually/audibly confirmed in this pass.

The Pi currently exposes no microphone capture device. Two-way speech and
acoustic echo cancellation cannot be verified until one is connected. The test
peer used file audio and a static outgoing image; incoming webcam frames were
decoded without saving a recording. This is a short regression check, not a
long-running reliability or latency benchmark.

Type checking does not replace runtime validation or protocol integration
tests. Generated `web/admin.js`, vendored dependency code and JavaScript test
fixtures are excluded; edit the source modules and regenerate the bundle.

## Physical HDMI-CEC verification

Follow-up on 6 October 2026 used the AIRHUG 02 pointed at the Samsung TV.
The terminal's CEC physical address was `2.0.0.0` (HDMI 2).

1. An Active Source announcement for `1.0.0.0` moved the TV away from the Pi
   to the unused HDMI input. The camera showed "HDMI Cable: Disconnected".
   A real incoming call to term2 then restored the Pi's call screen on the TV.
2. A Standby command blanked the physical TV. After a 12-second settling wait,
   the camera still showed a black screen. Samsung reported `to-standby`
   rather than a settled `standby` status. A real incoming call woke the TV
   and displayed the Pi's call screen; a subsequent power query reported `on`.

Both successful calls stayed connected for 12 seconds, decoded webcam video
continuously and ended cleanly. Received-video snapshots taken five seconds
after connection confirmed the physical screen, rather than just a CEC
acknowledgment. The outgoing peer used the SDK's static "no webcam" picture;
that picture on the TV was the expected call content. The terminal service
was left running and idle, with the TV on HDMI 2. These checks confirm the
current TV/port combination; they do not establish an exact wake-up latency.

The opt-in receiver check now supports an explicit snapshot for repeat tests:

```powershell
.venv/Scripts/python.exe zmala_terminal/tests/camera_feed_live.py --seconds 12 --snapshot build_tools/tmp/cec-call.jpg --output build_tools/tmp/cec-call.json
```

Run only with both terminals idle and the Pi set to auto-answer. Arrange the
camera to see the TV and establish the desired standby/other-input state
before dialing. Omit `--snapshot` for timing-only checks. Snapshots contain
the camera's view and remain in ignored local test output; they are not
repository assets. All nine TV-control unit tests also passed.

## Restoring TV state after incoming calls

The follow-up implementation remembers power before wake/configuration and
uses a separate CEC observer to retain routing state. Wake and restoration
share a lock; a new incoming call supersedes an older queued restoration.
Unknown input/power states are never replaced with guessed port numbers or an
unconditional Standby command. The installer enables the observer at boot.

On the Pi/Samsung combination, a 12-second call changed the TV from HDMI 1 to
HDMI 2; the webcam confirmed that it returned to HDMI 1 when the call ended.
Calls beginning with a black standby screen woke onto the terminal and returned
to a black screen afterward. The source cache also returned to the previous
HDMI address before sending Standby, retaining the input for the next power-on.

An unanswered-call check found and fixed cancellation during adapter setup:
configuring Playback can itself wake the TV, so this is marked as a change
before configuration begins. Stable observed power state takes precedence
over Samsung's stale transition replies. The TV-control tests cover these
races, duplicate restoration, unknown/stale state and superseded calls.

The final unanswered-call test cancelled two seconds after dialing. The CEC
trace and webcam confirmed restoration to standby after wake-up settled.
Standby retries are bounded and stop if another incoming call arrives; a TV
still booting can take several seconds to react to restoration commands.

Validation passed: `make lint`, 46 server tests, 76 terminal tests (three
hardware-dependent checks skipped), and three Linux package tests. The Pi
terminal and observer services were left running, with no active call and
the TV in standby.

Exact restoration requires that the source has identified itself or its route
has been observed since the observer started. CEC does not expose arbitrary
smart-TV app, channel or volume state; unsupported/unreported inputs use the
TV-native Inactive Source fallback, which this Samsung may ignore.

## Pi recovery and live server console (6 October 2026)

The installed Pi terminal was idle before these checks. Audio was excluded
because its webcam is due to be replaced.

- A controlled reboot started the display, CEC observer and terminal services
  automatically. The terminal registered, reported its home screen and executed
  a console command queued while its service was stopped. The command returned
  the new kernel boot ID. This is a reboot check, not a physical power-cycle test.
- A temporary blackhole route blocked access to the Windows server for 30 seconds.
  An independent systemd job removed it automatically. Management requests failed
  during the outage and resumed afterward; the terminal service PID stayed the
  same and a subsequent console command completed.
- Deauthorizing only the verified AIRHUG USB camera for five seconds simulated
  unplug/replug without touching the USB hub or network adapter. `/dev/video0`
  returned. Subsequent 12-second calls decoded continuous remote camera video
  without restarting the Pi app. Received webcam snapshots showed the physical
  TV displaying the caller; between standby-origin calls it returned to black.
- The live Linux console passed stdout/Unicode, stderr/nonzero exit, a five-second
  timeout, the 64 KiB output limit and successful execution after a timed-out job.
  The browser dialog submitted a command and displayed its result. It also removed
  an offline queued command and displayed the boot-queued command completing.
  Linux history prompts now show `$` instead of `PS>`.

Repeat the read-only live console checks only against an idle Linux terminal:

```powershell
node build_tools/test-console-live.cjs term2
```

The script requires the existing local administration configuration and, after
password setup, `ZMALA_ADMIN_PASSWORD` in its environment. It retains
test results in console history. It does not print tokens or execution leases.
Windows command execution remains covered by the terminal tests; no live Windows
terminal was started for this Pi-focused check.

Packaging now normalizes `.sh` line endings so a Windows checkout cannot produce
a Linux installer that fails on trailing carriage returns. A package regression
test covers CRLF conversion and unchanged binary assets. Both standard and
hardware-experiment archives include the CEC observer and boot service.
Both archives were copied to the Pi; checksums matched the local files, shell
syntax passed there, and the CEC files were present. This check did not reinstall
the working kiosk or run an installer on a fresh OS image.

All three live calls stayed connected for 12 seconds with sustained decoded
video. Final checks passed: `make lint`, 46 server tests, 76 terminal tests
(three skipped) and four package tests. The Pi services were left running and
registered with no active call, and the webcam confirmed the TV in standby.

After reboot the CEC cache starts unknown. The TV may not answer until the adapter
has a logical address, so an unobserved first-call baseline cannot be restored
reliably. Once observed, the later standby/input restoration checks passed. No
previous input is guessed from the Pi's own HDMI connector.

## Password administration — 6 October 2026

An isolated server passed remote first-password setup from the Pi, incorrect and
correct login, protected admin access, terminal/admin credential isolation and
logout invalidation. A disposable TLS certificate explicitly trusted by the test
client verified the HTTPS listener; tests also cover Secure cookie attributes.
The browser passed initial setup, sign-in error feedback, password change,
sign-out and sign-in with the replacement password.

Regression tests cover concurrent remote setup requests (only one succeeds),
password hashing, origin checks, old-token retirement, session expiry, restart
invalidation and bounded login/session state. `make lint` passed, as did 50 server
tests and 76 terminal tests (three skipped).

The main server was restarted without choosing the user's password. The Pi
confirmed that remote initial setup remains available on the live server, and
its authenticated terminal polling continued. HTTPS is optional and has not
been configured for this installation; the current LAN listener uses HTTP.

The password hash now persists separately in `data/admin-password.json`.
Regression coverage confirms legacy migration, deletion followed by restart,
preservation of accounts/settings, and fail-closed handling of damaged files.
Account saves do not recreate a deleted password file.

Raspberry Pi production servers now select
`/boot/firmware/zmalacall/admin-password.json` from the Linux device-tree model.
Windows, other Linux hosts and isolated test stores retain the data-directory
path. Path and migration/reset regressions passed; `make lint` and all 52 server
tests passed. The Pi 3's real device-tree model was checked over SSH. It runs the
terminal rather than the server and has no Node runtime, so no server/password
file was installed on its boot partition during this check.

## Incoming-call TV restoration policy

Rejection now cancels CEC wake retries and queues restoration immediately, without
waiting for a SIP end callback. Acceptance retains the original TV baseline until
the call ends. A TV already on and displaying the terminal receives no power or
source changes; volume and mute are never controlled. Unanswered calls and failed
calls continue to restore through the call-ended path.

Lint passed, all 81 terminal tests passed (three skipped), and all 52 server tests
passed on retry. The first server run hit an existing callback-test ephemeral
port forbidden by fetch (`bad port`), unrelated to CEC. All 27 CEC tests also
passed on the Pi. Both Linux packages were rebuilt; the shared call/TV modules
were copied from the local source into both installed Pi releases, and the idle
terminal was restarted. No new physical TV/call test was performed for this pass.

### Physical webcam verification on term2

Real incoming calls were tested with the Pi webcam pointing at the Samsung TV.
The initial photo showed BBC News, matching the observed TV source `0.0.0.0`.
An accepted call switched the physical screen to HDMI 2 and sustained the remote
camera stream for eight seconds. A separate call was rejected on the Pi before
answering (caller states 3, 4, 5, 14, 19).

**Built-in TV restoration failed physical verification.** After hang-up the
screen still showed the terminal carousel, even when the old implementation
reported a restored `0.0.0.0` route. Removing the external-source fallback for
the TV's own address did not reliably restore the broadcast picture either.
This Samsung refuses Give Tuner Device Status; remote-control broadcast/input
selection probes did not provide a reliable alternative. No volume or mute
commands were issued. Returning to the previous broadcast channel remains an
open hardware compatibility issue; these checks do not certify standby or
external-HDMI restoration under the new implementation.

The observer now clears a released route rather than continuing to report the
Pi as active after Inactive Source. Regression coverage checks native-source
restoration commands and released-route handling. All 30 CEC tests passed on
the Pi, all 84 terminal tests passed locally (three skipped), and `make lint`
passed. Both Linux packages were rebuilt and the Pi services restarted.

### Repeat restoration matrix on the Samsung TV

The TV was physically in standby at the start of the repeat test. An incoming
call rejected on the Pi before connection returned to a black screen; an
accepted incoming call displayed the terminal on HDMI 2, sustained video for
eight seconds, then returned to a black screen after the caller hung up.
Webcam photos verified both restored standby screens. The observer reported
`off: true`; the Samsung's direct power reply could still say `to-on` while the
screen was physically off. Restoration completed approximately 14–18 seconds
after rejection/hang-up, including the bounded standby retries.

The broadcast-channel rejection repeat started from BBC News, verified on the
webcam with a settled CEC power reply of `on` and source `0.0.0.0`. The call was
rejected on the Pi before answering. **Restoration failed:** the TV remained
on HDMI 2 showing the terminal carousel; the user independently confirmed it
had not returned to BBC. The terminal had correctly saved `off=False` and
source `0.0.0.0`, so this is a source-restoration failure rather than an incorrect
power baseline.

The accepted-call repeat also started from BBC, verified by the webcam and
settled `on`/`0.0.0.0` CEC state. The call connected, sustained video for eight
seconds, and ended normally. **Restoration again failed:** the webcam showed
the terminal carousel on HDMI 2 after hang-up, and the user confirmed the TV
had not returned to BBC. Both channel tests preserved power-on but failed to
restore the broadcast source. No volume or mute commands were issued.

### Samsung network fallback: verified restoration matrix

On 6 October 2026, the Samsung QE55Q60CAU exposed its authenticated remote
interface at port 8002. A paired `KEY_TV` command physically returned the
screen from HDMI 2 to BBC News; CEC source-release/routing probes had continued
to leave HDMI displayed even after the user changed TV settings.

The Pi was separately approved on the TV and paired. Its token and pinned
SHA-256 TLS certificate are stored privately in `/var/lib/zmalacall/tv-remote.json`.
The implementation remains optional, uses the existing background restoration
worker, and checks the certificate before sending credentials. A newer call
cancels pending restoration keys. Tests cover certificate mismatch, credential
redaction, authorization failure and cancellation during connection/power query.

The webcam pointing at the TV verified these real incoming-call results:

| Initial physical state | Call outcome | Physical result |
| --- | --- | --- |
| BBC News, on | Rejected before answering | Incoming-call screen on HDMI 2, then the same BBC News channel |
| BBC News, on | Answered, caller hung up | Call screen on HDMI 2, then the same BBC News channel |
| Standby, black screen | Rejected before answering | Incoming-call screen on HDMI 2, then black standby screen |
| Standby, black screen | Answered, caller hung up | Call screen on HDMI 2, then black standby screen |

Both answered calls sustained received video for eight seconds. Their caller
states were 3, 4, 5, 7, 8, 14, 19; rejected calls reached 3, 4, 5, 14, 19 without
connecting. Photos of the physical TV, rather than CEC acknowledgements alone,
confirmed the results. The caller intentionally used the SDK's static picture;
the Pi webcam supplied the TV view, so the large no-webcam picture shown on the
TV during these test calls is expected.

Testing also found that this TV ignored CEC Standby after returning to its
tuner. `KEY_POWEROFF` did not work either. The paired power-key fallback now
runs only after the CEC retries still report settled **on**, and rechecks that
state immediately before sending Samsung's toggling `KEY_POWER`. Off, unknown
and transitional replies never trigger a toggle. This restored physical standby
in both final tests, about 24–27 seconds after call termination with the current
CEC retry delays. The initial standby setup attempt remained physically on and
was excluded from the standby results; the repeats began from verified black
screens. No volume, mute or channel-number commands were sent.

`make lint` passed. All 99 terminal tests completed successfully (three skipped);
the Pi passed all 34 CEC/call-control and 11 Samsung-remote tests. Both installed
Pi releases received the local source changes and the terminal was restarted.
Both Linux release archives were rebuilt. Live-TV restoration is verified for
this Samsung; restoration of a particular smart-TV app remains unsupported.

### Nuroum C20 integration (9 October 2026)

The server saved term2's C20 camera, microphone and speaker selections. The
restarted Pi reported all three devices plus the C20 as its ringer; these
selections persisted across subsequent restarts. HDMI audio was not selected.
The speech audio profile remained active.

A Windows-to-Pi call connected and sustained decoded C20 video throughout
15 seconds, with a maximum notification gap of 1.06 seconds and a final receive
rate of 14.99 fps. A received snapshot showed the physical TV displaying the
test caller's static image. Video was 640×480: the SDK selected the camera's
raw format, rather than its HD MJPEG format, despite the saved 720p target.
Audio traffic flowed in both directions; on the Pi, the C20 capture and
playback streams ran at their native 16 kHz and 48 kHz stereo rates.

The hardware encoder's capability ladder was extended to include all server
presets. The original probe was reported as passing 640×360, 1280×720 and
1920×1080 selection, but the 10 October readback check disproved the 640×360
result: both installed SDKs reject that size without a return-code failure.
The low preset is now 480p (640×480), with migration of saved 360p settings.
`zmala_terminal/tests/video_settings_native.py` checks the actual SDK size and
NACK enablement for each preset without starting a call. Configuration checks
do not establish HD capture or HD call reliability.
A temporary V4L2 conversion trial remained below HD and was removed.
No listener was near the Pi, so speaker audibility, speech quality and echo
performance remain unverified. The app was left running for a listening test.

`make lint` passed; all 99 terminal tests completed successfully (three skipped).
Both Linux package variants were rebuilt with the updated encoder source.

### C20 HD capture and minimum 10 fps (9 October 2026)

The optional hardware package now registers `ZmalaMJPEG: /dev/video0` through
public SDK interfaces. It requests MJPEG explicitly and rejects dimensions
that the driver silently clamps. Capture runs off the ticker, retaining only
the newest compressed camera frame. Server camera/resolution settings select
this path; C20 microphone, speaker, ringer and speech audio remain selected.

| Check | Actual result | Meets 10 fps |
| --- | --- | --- |
| 720p, 30-second call, static incoming video | 1280×720 received, minimum 14.41 fps after startup | Yes |
| 720p, 45-second call, occupied PC webcam | 1280×720 received, minimum 14.69 fps; PC sent a 1 fps placeholder | Receive only |
| 720p, 60-second call, moving SDK test pattern | 1280×720 received, minimum 14.26 fps; 1280×720 sent at 15 fps | Yes |
| 1080p native hardware/FFmpeg roundtrip | 144 correctly sized decoded frames in 10 seconds | Local probe only |
| 1080p native hardware/OpenH264 roundtrip | 94 correctly sized decoded frames, growing ticker delays | No |
| 1080p, 30-second connected call | Video RTP present, zero decoded frames, OpenH264 errors | No |
| 1080p call with incoming moving pattern | Camera stopped delivering; 704×576 placeholder at about 1 fps | No |

The moving-pattern 720p call maintained decoded notifications through second
59, with a maximum gap of 1.063 seconds. The snapshot showed the actual TV
displaying the moving pattern and was exactly 1280×720. Final video statistics
were 14.84 received fps, 15 sent fps and about 189 ms jitter buffer. Audio RTP
flowed both ways (19.2/42.4 kbps at the last sample). A five-second CPU sample
during this connected call measured 197.2% of one core for the terminal process.
No listener was available to verify C20 audibility, echo or speech quality.

The occupied PC webcam initially made `--camera` appear to pass on receive
alone. The fixture now checks both sent and received rates for moving-source
tests, rejects missing/zero/invalid FPS, and supports `--synthetic` so testing
does not require the user's PC webcam. Config-transition calls that never
connected and calls made while USB capture was stalled are excluded from the
successful resolution evidence. The C20 stall required a Pi reboot; changing
resolution alone did not recover it. Native V4L2 attempts to request 15 camera
fps were clamped by this camera to 30 fps.

Term2 is left on 720p with explicit MJPEG capture and C20 audio. These short
tests establish the highest working server preset tested at the required
frame floor, rather than claiming that 1080p hardware capability guarantees
reliable calls or that the current USB recovery issue is resolved.

After deploying the final plugin and restarting the terminal service, another
30-second moving-pattern call passed at a minimum received rate above 14 fps.
The app remained registered and idle afterward. `make lint` passed and all
104 terminal tests completed successfully (three platform-dependent tests
skipped). The native plugin compiled on the Pi with warnings treated as errors;
both Linux package variants were rebuilt. Windows implementation and server
account associations were retained.

### Single C20 Linux media path (9 October 2026)

Linux now uses one C20 configuration: explicit MJPEG camera capture, Pi V4L2
H.264 encoding, FFmpeg software decoding and C20 microphone/speaker/ringer.
Windows retains server-selected SDK devices. The obsolete C930e capture bridge,
hardware-decoder mode, media-mode launch scripts and local video overrides were
removed. Native source is under `zmala_terminal/media/`; the standard installer
builds both private plugins and removes obsolete systemd media drop-ins.
The hardware encoder reuses writable raw frame buffers instead of allocating
one for every input picture. Shared SIP, UI, provisioning and CEC code remain.

The normal package was installed on the Pi through `install.sh --user pi3
--wifi-mode existing-link`. Its ordinary kiosk service starts at boot, loads
the native plugins without experiment flags and reports only the C20 camera
and audio devices. Enrollment, account association and TV pairing survived.
Native compilation passed with warnings treated as errors, and the no-camera
encoder preset probe passed all three server resolutions. `make lint` passed;
107 terminal tests passed on Windows (three skipped) and the Pi (two skipped),
along with four Linux packaging tests.

A 60-second moving-pattern call passed at 1280×720, minimum 14.30 received fps
and 15 sent fps. Its snapshot showed the physical TV displaying the pattern.
The following 45-second call failed: camera frames stopped and the SDK used a
one-fps placeholder. A standalone camera probe also received zero frames.
CPU samples from that failed call are excluded. After a Pi reboot, a 45-second
call passed at minimum 14.12 received fps and 15 sent fps. A five-second CPU
sample during that passing call was 168.9% of one core; this does not establish
a controlled performance improvement. The C20 capture stall is therefore not
limited to 1080p and camera recovery remains unresolved.

The user paused testing after the recovered call ended. No further calls or
restarts were made in that session; the terminal was left registered and idle
at 720p with C20 audio. Subjective audibility and echo quality remained unverified.

## Pi 4 HDMI-CEC recheck — 11 October 2026

The Pi 4 selects `/dev/cec0`, mapped to the connected HDMI output, and reads
physical address `1.0.0.0` for the Samsung's HDMI 1 input. `/dev/cec1` has no
physical address. The routing observer and terminal use the same adapter.

The migrated Samsung pairing initially reached the TV but timed out waiting
for authorization. The C20 view showed the permission prompt. A fresh pairing
request, retaining verification of the stored certificate pin, succeeded after
the user selected Allow. The private credentials were updated on the Pi only.
No CEC application-code change was needed.

The C20 was pointed at the TV for physical verification:

| Test | Observed result |
| --- | --- |
| Live BBC News → terminal wake → restore | Terminal appeared on HDMI 1, then BBC News returned on the same channel |
| Standby → terminal wake → restore | Black screen → terminal → black standby screen |
| Actual incoming call from live TV, auto-answer, caller hang-up | Physical call picture with live 1080p video, then BBC News returned |
| Actual incoming call cancelled after two seconds from standby | No answer; TV returned to black and remained black at a later check, over a minute after cancellation |

Standby restoration with the known tuner source took roughly 25–30 seconds:
this TV ignored CEC standby after tuner restoration, so the existing guarded
Samsung network fallback was used. During the cancellation repeat the TV
reported `to-on` despite a physically black screen; the observer retained its
standby state. A transition reply alone is not reliable evidence of the screen.

One earlier cancellation attempt had an inconsistent starting state: the
setup photo was black, but the app's initial power query reported on and its
source was unknown. The user confirmed no remote buttons were pressed. The app
consequently left the TV on after cancellation. The cause of that power-state
discrepancy remains unresolved; this is not counted as a successful standby
test. The repeat checked
the standby baseline over several queries before dialing and restored it.

The first answered-call attempt also encountered the pre-existing C20 USB I/O
fault and received no camera video. After a targeted USB reset, the repeat
delivered 1920×1080 video and supplied the physical-TV snapshot. CEC success
does not resolve this independent camera reliability issue.

All 55 CEC adapter, TV/call-control and Samsung remote unit tests passed.
The normal applications and terminal HDMI view were restored after testing.


### Broadcast-to-terminal first press — 11 October 2026

Physical feedback exposed a gap in the earlier CEC test: the Pi's transmitted
Active Source announcement and its own desktop screenshot did not prove that
the TV had left broadcast. The television could acknowledge CEC while still
showing the tuner. Adding Set Stream Path was not sufficient in the full test,
and the Samsung network `KEY_HDMI1` command was also ignored.

The already-paired Samsung remote's `KEY_HDMI` command did select the terminal,
confirmed at the TV. Its use is now explicitly bound in private runtime
configuration to physical address `1.0.0.0`. In the integrated repeat, a single
navigation press from broadcast was consumed, the log recorded `KEY_HDMI`, the
selected contact remained unchanged, and the user confirmed the actual TV
showed the terminal UI. The fallback is restricted to an awake native-TV source;
standby wake continues through CEC. All 198 terminal unit tests passed (three
platform skips), including source binding, token refresh and cancellation checks.


### Configurable return to TV — 11 October 2026

The terminal and server now share `tv_idle_seconds`: 30 seconds (default),
1/2/5/10/20 minutes or Never. Both test terminals were set to 30 seconds.
On term2, captured bottom-edge pixels confirmed the three-pixel blue bar is
hidden for the first ten idle seconds, appears with the remaining time,
disappears on another press, and reappears after ten more quiet seconds.
The expiry log occurred thirty seconds after the last activity. The user
confirmed the TV returned to broadcast in the integrated test.

A standby repeat exposed two visibility/wake queries observing different
power states. The controller now carries the state captured at the first
press through to the wake worker. The repeat saved `off=True`, returned to the
tuner at expiry, and finished the existing bounded standby sequence with the
paired Samsung power fallback roughly 25 seconds later. The observer then
reported standby, and the user confirmed that the physical TV was off.
Transition power replies from this model remain unreliable; observer messages
alone are not treated as proof of the physical display state.

Validation: 210 terminal unit tests passed (three platform skips), 75 server
tests passed, TypeScript/ESLint/Ruff passed, and the real Tk settings layout
passed all 95 languages at 900×620 and 1280×720. A separate Pi/Xvfb render
verified the French timeout choices and the bar at the absolute bottom edge.
Tests cover authenticated persistence, invalid values, legacy defaults,
activity and call pauses, discarded drafts, and superseded TV restoration.
