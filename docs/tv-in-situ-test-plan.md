# TV control during real incoming calls

## Purpose and scope

Use the deployed term2 terminal and its Samsung Q60C, with the C20 pointing at
the TV. Exercise the normal incoming-call, answer and hang-up paths. Standalone
plugin results are not evidence that the call controller invokes that plugin.
This deployment experiment supplements HLR-TERM-TV-018 and the fixture test
T-HLT-027; media observations use the approach of hardware scenario T-HLT-004.
It introduces no new product requirement. Private photographs, call logs and
configuration backups must not be committed.

## Preparation

1. Confirm no active family call; verify server registration and deployed TV
   controller/plugin versions. Record TV qualification flags and current state.
2. Use the separate term1 account on Windows. Stop any existing term1 GUI before
   running a caller with that enrollment; never run two registrations for it.
3. Record auto-answer settings and temporarily enable a bounded answer delay on
   term2 if needed. Restore them after testing. Do not alter TV volume/mute.
4. Confirm the USB-connected OnePlus identity and availability; use it for a
   supplementary incoming call if it is unlocked and controllable.
5. Enable developer access only for the experiment, with host-key verification.
   Use bounded diagnostics and restore normal service/camera ownership afterward.
6. Before ringing and after hang-up, photograph the TV only while the camera is
   free. During the call, obtain the C20 image through received video on term1;
   do not open a second camera stream competing with the call.

## Matrix and acceptance

Run each baseline scenario twice if the first run completes; preserve failures.

| Case | Initial state | Action | Expected visible behaviour | End state |
| --- | --- | --- | --- | --- |
| OFF-1/2 | Confirmed standby | term1 calls; term2 answers | TV wakes, terminal incoming/call UI becomes visible; received C20 video confirms the physical TV picture | Caller hangs up; inactivity bar appears, then TV returns to standby after the configured delay |
| TV-1/2 | Live broadcast picture | term1 calls; term2 answers | TV changes to terminal HDMI and shows the call | Caller hangs up; inactivity bar appears, then live TV returns after the configured delay |
| CANCEL | Live TV | term1 cancels while ringing, before answer | Call UI clears; no delayed source switch after cancellation | Terminal remains visible until the fresh inactivity delay expires; then live TV returns |
| PHONE | Live TV | OnePlus calls term2, then hangs up | Same terminal routing and restoration with Android caller | Live TV returns after the inactivity delay |

For each case record monotonic times for dial, connected, first decoded frame,
hang-up and observed restoration; record sampling uncertainty. Save before,
in-call and after pictures, state getter answers, relevant journal events and
actual result. Record the configured Return to TV delay and wait for it to expire without
input; the blue bar should appear after ten seconds. Allow up to 30 additional
seconds for routing/restoration, recording actual latency. Repeat with a button
press resetting the countdown, and with Never disabling automatic return.
Confirm the physical screen, not just CEC acknowledgement or setter success.
Record missing pictures, media failure, timeout or unavailable phone as failures
or not-run, never as passes. Abort on an unrelated family call.

## Investigation and cleanup

If the controller bypasses the improved plugin or captures the wrong original
state, retain the failing baseline and identify the owning code/requirements
before changing it. Retest affected cases after any fix. Keep unrelated TV
settings and enrollment intact. End all test calls, restore temporary profile
settings and prior term1 launch state, verify term2 remains registered, stop
verbose diagnostics and disable developer access. Produce a local HTML/photo
report and record the measured outcome below.

## Historical results — 30 October 2026

These runs predate the post-call inactivity policy. Their immediate-restoration
timings describe that older build, not acceptance of the current test matrix.

The test used the deployed Samsung driver with the existing, unchanged call
controller. OnePlus/Antoine replaced term1 as the principal caller after the
Windows probe connected but failed to decode video. Audio quality was not tested.
The phone screenshots show the C20's physical view of the TV, including the
phone camera image displayed on the TV when both video directions worked.

### Deployment mismatch found

The installed setup record had power passed, source failed/continued without,
and no `network_paired` flag. The paired credential file existed, but the normal
call path disabled its use. With this original configuration, the standby call
left the TV on live broadcast after hang-up; a call from live TV did not switch
to HDMI. These are not passes. Source-only qualification enabled HDMI switching
but did not enable the paired return-to-TV command.

The original record was backed up. Later cases temporarily enabled both source
qualification and the existing pairing, following the separately observed
standalone source round trips. These test flags are not a new user confirmation.

### Calls with source and pairing enabled

| Evidence prefix | Initial state | In-call observation | After hang-up | Result |
| --- | --- | --- | --- | --- |
| `paired-tv1` | Live broadcast, photographed | Terminal picture and both video views | Live broadcast photographed | Pass for this sampled cycle |
| `paired-tv2` | Live broadcast following prior restore | Terminal picture; source commands recorded | State query reported tuner, but photo overlapped preparation of the next standby test | Restoration visual evidence invalid; not counted as a full pass |
| `paired-off1` | Standby, photographed; controller captured off=true | Terminal picture and both video views | Standby photographed and queried | Pass for this sampled cycle |
| `paired-off2` | Standby, photographed and queried | Terminal picture and both video views | Standby photographed and queried | Pass for this sampled cycle |
| `paired-tv3` | Live broadcast after explicit wake and tuner selection | TV displayed “Check Device Power” instead of terminal picture, although the call/C20 video continued | Live broadcast photographed | Fail: intermittent HDMI picture loss |
| `paired-cancel` | Live broadcast | Cancelled at about 6 seconds from dial; no connected event | Live broadcast photographed; no later HDMI switch in the observation window | Pass for this sampled cancellation |

SIP connection took about 11–14 seconds after incoming-call receipt in the paired
cases, including the temporary five-second auto-answer delay and TV settling.
Successful calls showed both video directions in the 25-second sample after dial;
these sampled screenshots do not establish exact first-frame latency. Restoration
completion logs were roughly 6–7 seconds after live-TV hang-up and 25–27 seconds
after standby hang-up. Physical after-pictures were taken after the 30-second
observation wait plus capture overhead, not continuously during restoration.

The HDMI failure had active display/compositor/terminal services and a connected
DRM HDMI connector. This does not identify whether source selection, HDMI signal
recovery or Samsung firmware caused it. It must be investigated before declaring
the integration reliable. The normal call worker also still uses direct CEC
Image View On rather than the driver's new guarded wake API; these calls do not
qualify that API's use by normal calls.

Private evidence is under `build_tools/tmp/tv-real-calls/` (HTML, photographs,
phone screenshots and journals). It is deliberately excluded from Git. No
requirement verification status or persisted qualification is promoted by this
experiment. Cleanup completed: auto-answer restored to off/10 seconds, the original setup
record restored byte-for-byte, developer access disabled, test calls ended and
terminal service restarted successfully. Term1 was not running beforehand and
remains stopped. The TV was left showing live broadcast. No production code was
changed during this experiment.

The requirements validator/report builder passed (invoked directly after the
local `make.exe` failed to start). Existing implementation requirements, trace
comments and user workflows are unchanged. The technical guide now explains the
setup gates and the remaining call-worker wake limitation. No unresolved result
above is presented as passed; these historical results do not fully qualify the TV.


## Normal-call follow-up — 30 October 2026

Issue #46 follows the failed real-call qualification above. Normal call wake now
uses the qualified model driver's guarded `set_power_on` before CEC fallback,
with a cancellation check after driver I/O. Restoration may delegate ambiguous
CEC results to the driver's independently guarded power-off operation. The
controller and Samsung plugin are installed on term2; journals confirm normal
calls invoke the model driver's wake method.

The controller change alone did not eliminate “Check Device Power”: `fix-tv1`
and `fix-off1` still failed. The Pi reported an active 1280x720 HDMI output with
DPMS disabled. Resetting the output did not immediately resolve the picture.
The TV's Universal Remote setup contained an obsolete Sky profile assigned to
the Pi's HDMI2 input. Only that profile was removed; the other Samsung device
profile was left untouched. This is a useful configuration finding, not proof
that it was the only cause.

After removal, actual phone calls alternated live TV, standby, live TV, standby:

| Evidence | Result |
| --- | --- |
| `verified-tv1` | Both video views visible by the 25-second sample; live TV restored. |
| `verified-off1` | Both video views visible by the 25-second sample; standby restored. |
| `verified-tv2` | Both video views visible by the 25-second sample; live TV restored. |
| `verified-off2` | Failed wake/picture: still ringing at 25 seconds; connected around 31 seconds; the 35-second C20 view showed a dark TV. Afterward power reported off. |

The final case sent the guarded network power key, then spent about 23 seconds
in input selection before starting the five-second answer countdown. Command
acceptance did not prove visible wake. Saved observations do not distinguish a
power-state race from a missed wake; the issue remains open. No further phone
calls or cancellation retest were made because the user needed the phone back.
The phone was left on contacts, automatic answer restored to off/10 seconds,
developer access disabled, and terminal/display/compositor services checked
active. The TV was left in standby. The source and network-control flags remain
enabled so the installed normal-call integration can be exercised; the original
setup record is retained in `tv-check.in-situ-backup.json`. These manually enabled
flags do not represent a completed user wizard or full reliability qualification.

Focused checks: 80 tests passed; one display-dependent HLT was skipped on Windows.
Python lint and the requirements report builder passed. The helper guide source
and Word document were updated and the generated eight-page release PDF visually
reviewed. Native Word rendering was unavailable because LibreOffice is absent.
Private photos, timestamps and journals remain under `build_tools/tmp/tv-real-calls/`.
These results do not establish that this TV is fully fixed. Repeat physical
qualification before claiming reliable wake and picture restoration.


## Offline maintenance review — 31 October 2026

The self-test branch was reconciled with the current terminal call/idle policy.
Camera capture and bounded process cleanup are separate helpers. Camera loss
stops further experimental commands while preserving observations and attempting
restoration; child cleanup failures and a timed-out service stop still trigger
terminal restart. Local regression fixtures exercise these failures without a TV.
The tool remains opt-in and never marks setup checks passed automatically.

No term2 access, deployment, calls or TV tests were performed during this cleanup.
The intermittent wake/picture findings above remain unresolved hardware findings;
passing local tests or merging the tool is not a new physical qualification.
