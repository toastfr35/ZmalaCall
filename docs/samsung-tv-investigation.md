# Samsung Q60C plugin investigation — 30 October 2026

This is an engineering evidence summary, not a qualification claim for all
Samsung TVs. The generic repeatable test procedure is in `new_TV.md`.

## Hardware and observations

- Model reported by local metadata: **QE55Q60CAUXXU**, Tizen. Firmware field
  returned `Unknown`; the actual firmware version was not established.
- Pi connector: physical address `2.0.0.0` (TV HDMI 2), detected CEC adapter.
- Developer SSH tunnel was used for all terminal operations, with both SSH
  identities verified. Camera images and credentials remain private.
- `cec-client -l` enumerated both Pi adapters. Bounded `cec-ctl` operations were
  used with the existing CEC observer; a competing interactive CEC client was
  not left running. The adapter initially had no logical address; configuring
  a playback identity restored power queries. Construction/getters do not
  silently configure an adapter or change TV state.
- In standby, CEC returned `to-on`, while local `/api/v2/` metadata returned
  `standby`. After wake both reported on. After standby, CEC also returned
  `to-standby` rather than a settled state. The HTTPS remote port became
  unavailable in standby while HTTP metadata remained reachable.
- CEC Image View On woke the TV. Pinned Samsung `KEY_HDMI` selected the existing
  verified HDMI-2 binding. `KEY_TV` returned to live terrestrial TV and retained
  the displayed channel. No TV volume, mute or channel keys were sent.
- CEC standby worked from HDMI during standalone investigation but was ignored
  from the tuner in a later controller experiment. Guarded paired power-off
  worked during the direct plugin runs. This reinforces retaining both transports.

## Candidate changes and capability decisions

The seven-method API is unchanged. Settled CEC power takes precedence; absent or
ambiguous CEC power now falls back to fresh local metadata. Only `on` and
`standby` are accepted. Unreachable endpoints, redirects, malformed/oversized
responses and unrecognized values remain unknown. Power-off still checks again
following TLS authentication and does not blindly toggle. HTTP metadata is an
unauthenticated local observation; no credentials are sent there, while commands
retain certificate pinning. Current-input and wake capabilities require bounded
controller-supplied CEC callbacks. Model lookup and power metadata work without
them. No new input identifiers or SmartThings dependencies were added.

The user narrowed this work to plugin testing. The original terminal controller
was restored; candidate controller-integration changes were not retained.

## Direct physical test evidence

Three direct plugin cycles completed: wake, select terminal HDMI, select live
TV, power off, repeat power off. Photos were inspected for HDMI, tuner and dark
screen; reported power matched those states. Repeated off requests left the TV
in standby. Command-call durations (not visible-completion timings) ranged from
approximately 0.06 seconds for CEC wake to 4.62 seconds for a paired HDMI command.
The snapshots used fixed settling delays rather than continuous timing analysis.

These are smoke tests, not long-term reliability evidence. Actual phone calls,
other HDMI devices, smart-TV apps, cold boots, HDMI cable moves, revoked pairing,
long standby and a different firmware/model were not physically qualified here.
A preliminary controller restoration experiment did not finish inside its
25-second observation window; a later longer run restored a tuner/on baseline.
Neither is counted as a real-call test. No Android phone was connected over USB.

The first generic self-test completed 11 photographed steps and restarted the
terminal service. All setters returned acceptance, and reported states matched
requested power/input. However, steps 8–11 showed a dark picture after wake,
except for a tuner OSD banner in step 10. The panel could be on without a live
programme picture; successful visual restoration is therefore **not confirmed**.
The bundled report records this discrepancy for investigation, rather than
claiming the plugin is fully qualified. HDMI selection is identifiable by the
TV's HDMI-2 banner; its picture is blank while the terminal service is paused.

The generic self-test bundle provides a separate complete action/photo record.
Its report deliberately does not turn setter acceptance into an automatic pass.
Unit tests cover unknown/error observations, response limits, cancellation,
certificate pinning and power-toggle guards. Development-tool regressions live
under `tests/adhoc/`, outside the runtime requirements baseline.

## Rollback and privacy

A private on-Pi backup preserves the original plugin, controller and pairing file.
Its exact path and access details are in ignored local hardware records. Rollback
restores those files while the terminal is idle, then restarts its service.
The candidate preserves pairing and source-binding data. There are no end-user
setup workflow changes, so the user guides require no new instructions.

## Expanded transition run

The revised generic runner completed 23 photographed steps with five-second
settling delays, beginning with initial/off/on/on. It exercised per-input
idempotence and power cycles, both directed input transitions, then restoration.
The fullscreen colour-bar card is clearly visible at step 10, and live TV at
step 11. Steps 5–6 accepted HDMI selection but reported tuner; their photos did
not confirm the test card (a TV source/pairing screen appeared on repetition).
Step 15 accepted wake but still reported standby. Subsequent source transitions
were therefore inconclusive because the TV remained off. Restoration showed
live TV again and the terminal service restarted. This candidate is not fully
qualified; retain the failure evidence and investigate before release.

## Timed observations at 5, 10 and 15 seconds

A further 23-step run on 30 October 2026 captured 67 photos: the initial state,
then three observations after each command, without another setter between them.
All photos were visually reviewed. Standby, wake from each input, repeated
commands, both directed input transitions and restoration showed the expected
picture in every first sample; all reported power/input samples agreed.
The HDMI test-card clock and live programme advanced across later samples.

Observation routines started at their scheduled offsets; photos completed about
3.46–3.69 seconds later because the camera was opened and warmed for each capture.
These are not measurements of exact visible-completion time. No transition in
this run first became correct at the second or third observation. The increased
spacing between successive commands is another changed variable, so the result
is consistent with settling time helping but does not establish causality or
remove the earlier intermittent failures. Repeat qualification remains necessary.
The original runtime plugin was restored, the terminal service was confirmed
active and developer access was disabled after testing. Private photos and the
reviewed HTML/ZIP are retained locally, outside version control.

## Continuous-camera settling comparison

Three further trials used the same candidate, on/tuner baseline and 23-step
sequence, with one observation per command at 5, 10 or 15 seconds. The camera
stayed open and drained frames throughout each trial; frame reads occurred
approximately 44–81 ms after the target. All 69 photos were visually reviewed.
Power and input getters ran after every photo, and all 66 setter/state comparisons
matched. Those matches did **not** establish that the programme picture was ready.

- At 5 seconds, initial wake and repeated on were dark (steps 3–4). Later tuner
  wake was also dark, and re-selection showed only an OSD banner (15–16).
- At 10 seconds, initial wake was dark and repeated on showed only a banner
  (3–4). Later tuner wake and re-selection showed live television.
- At 15 seconds, initial wake showed only a banner and repeated on was dark
  (3–4). Later tuner wake and re-selection showed live television.
- In all three trials, standby photos were dark; HDMI wake, HDMI/tuner switching
  and final restoration showed the expected pictures. The terminal card clock
  advanced between samples.

Thus a blanket 15-second wait is not a demonstrated remedy. Reported on/source
state must not be interpreted as visible playback readiness. The experiments
changed both standby dwell and post-command observation time; sequential trial
order and one run per interval also limit causal conclusions. The next focused
investigation should isolate wake from tuner versus HDMI, holding standby dwell
fixed, and observe picture recovery without intervening setters. No production
wake delay or controller behaviour was changed by this experiment.

The runner now records actual frame-read, getter-start and inter-command timings.
Its continuous camera child has bounded readiness/capture waits and is stopped
before the terminal resumes. Tool tests cover next-frame capture, single-sample
scheduling, query overhead, process failure and timeout. Runtime requirements and
user workflows remain unchanged. The original plugin was restored and developer
access disabled; private HTML/photo evidence remains outside Git.
