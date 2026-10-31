# Investigating a TV and developing its ZmalaCall driver

This is an engineering work plan, not a new product requirements baseline.
Use term2 and its Samsung TV as a rehearsal for supporting an unfamiliar TV in
someone else's home. Keep the working Samsung driver available for rollback;
investigate the TV's behaviour independently before using that driver as a comparison.
Do not replace a working installation until the candidate has passed its checks.

## 1. Establish access and a reliable view

- [ ] Agree a test window with the person at the terminal. Explain that the TV
  will change inputs and may enter standby. Check that no call is in progress.
- [ ] Enable **Terminals → Developer access** for the selected terminal on the
  server. Only one terminal can have this access at a time.
- [ ] From a PC on the server's wired local subnet, connect through the server:

  ```sh
  ssh -J SERVER_USER@SERVER_LAN_ADDRESS -p 22001 PI_USER@127.0.0.1
  ```

  Use the normal server and Pi login credentials. Verify both SSH identities
  against trusted records. The same loopback address can lead to different Pis;
  investigate a changed-key warning rather than disabling verification. Keep
  private addresses, passwords, tokens and host-key records in ignored
  `hw_setup.md`, not in this document or the public repository.
- [ ] Confirm the hostname and terminal service before issuing commands. Verify
  that disabling developer access closes the tunnel when doing initial setup.
- [ ] Point the C20 at the whole TV, including any status LED. Capture a fresh
  frame and check that menus, input labels and pairing prompts are readable.
  The user has repositioned term2's C20; verify its actual view before testing.
- [ ] Establish a bounded camera-only preview or timestamped snapshots, using one
  camera owner at a time. Coordinate with terminal media/USB power management:
  a normal video call is unsuitable as the observation channel because it also
  activates TV control. Stop the preview before testing actual calls, and restore
  normal media and USB power ownership afterward. Developer access does not itself
  provide a camera viewer or keep the C20 awake.

**Evidence:** verified terminal identity, a current TV image, initial TV state,
and a local person available for pairing prompts or recovery when necessary.

## 2. Inventory the TV and preserve the installation

- [ ] Record manufacturer, exact model, firmware, region, HDMI socket used by the
  Pi, and any AVR/soundbar between them. Identify the active Pi DRM connector and
  associated CEC adapter; do not assume `/dev/cec0` or HDMI 1.
- [ ] Record CEC settings and vendor names (Samsung: Anynet+), network standby,
  remote-control permissions and any relevant energy-saving options. Record
  changes explicitly so they can be restored.
- [ ] Identify the TV's local network address from trusted local inventory.
  Record whether it remains reachable during standby and after a cold start.
- [ ] Back up the installed driver, registry, controller configuration and private
  pairing/source-binding file with ownership and permissions. Record software
  revision and a recovery procedure before modifying the Pi.
- [ ] Record baseline power, current source, channel if visible, TV volume/mute,
  and normal call behaviour. TV volume/mute must remain unchanged by the tests;
  ZmalaCall uses the C20 for call audio.

For the Samsung rehearsal, the previously discovered model is **QE55Q60CAUXXU**.
Treat this as a starting observation, not proof that another firmware or Samsung
model behaves identically. Leave SmartThings out of this investigation unless
separately requested.

## 3. Investigate transports, starting with observations

1. **HDMI-CEC:** inspect adapter/connector details, physical/logical addresses and
   bounded power queries. Observe routing events while a person selects the tuner,
   the Pi HDMI input and another source. Compare every report with the C20 image.
   Coordinate with the existing CEC observer; avoid a competing process that
   reconfigures adapter identity or consumes the events being measured.
2. **Local network control:** consult the manufacturer's current documentation,
   then inspect read-only model/status responses from the identified TV. Determine
   pairing/authentication, supported commands, response semantics and timeouts.
   Avoid broad network scans, undocumented service-menu commands and factory resets.
3. **Pairing:** have the local person accept any on-screen permission. Keep tokens
   private. For a self-signed endpoint, establish and retain a trusted certificate
   pin; verify it before sending credentials on subsequent connections. A changed
   pin is a repair/pairing event, not a reason to disable verification.
4. **Wake and standby:** test discrete commands first. Check repeat requests in
   both states, long standby, network unavailability and transitions. A successful
   network request does not prove that the TV is on. Avoid blind power toggles.
5. **Input selection:** find stable identifiers for sources that can both be
   observed and selected again. Test direct selection, including return from the
   tuner. An input menu opening is not equivalent to selecting an input.

For the rehearsal, compare the measured behaviour with Samsung's existing local
metadata/pairing integration and CEC callbacks only after recording observations.
Do not copy its capabilities onto a new model without evidence.

Use a private experiment log:

| Time / case | Initial visible state | Operation / transport | Raw response | Reported state | C20 observation and delay | Outcome |
| --- | --- | --- | --- | --- | --- | --- |
| Example | Live TV | Select verified Pi HDMI | Sanitized response | Input identifier or unknown | UI visible after measured delay | Pass / fail / inconclusive |

Keep tokens out of logs. Store household images and raw captures privately.
Distinguish a command being accepted, a reported state changing and the visible
picture changing. A blank screen alone does not prove standby; a stale CEC routing
event alone does not prove the currently displayed source.

## 4. Decide what the driver can truthfully support

Use the existing API in `zmala_terminal/linux/tv_plugins/api.py`:

| Method | Decision to establish |
| --- | --- |
| `get_model()` | Reliable model string, or `None` if unavailable |
| `get_capabilities()` | Supported optional method names, based on available mechanisms |
| `get_power_status()` | Observed `True`/`False`; `None` for unknown or transitioning |
| `set_power_on()` | Safe on request without an unconditional toggle |
| `set_power_off()` | Safe standby request without an unconditional toggle |
| `get_current_input()` | Observed, restorable identifier; otherwise `None` |
| `set_current_input(input_id)` | Select a specific supported identifier |

Setters return command acceptance/already-observed target state, not proof of
visible completion. Unsupported optional methods are omitted from capabilities
and raise `NotImplementedError`. Temporary unavailability is different from an
unsupported operation. Capabilities do not replace the setup wizard's physical
qualification of power and source control.

No `get_inputs`, channel control or TV volume API is required. If a smart-TV app
or another source cannot be identified and restored, document that limitation;
do not guess an input. If visibility cannot be established reliably, leave
visibility-dependent automation unqualified rather than treating unknown as visible.

**Decision gate:** write a capability/limitation table and choose CEC, local network
control, or a combination for each supported method before implementing setters.

## 5. Implement the candidate without duplicating controller policy

- [ ] Create a GitHub issue and feature branch. Review the existing TV requirements,
  especially `HLR-TERM-TV-018` and `LLR-TERM-TV-033`, their linked requirements,
  implementation traces and verification plans before editing.
- [ ] Put the implementation in
  `zmala_terminal/linux/tv_plugins/<model_family>/driver.py`, exporting one
  `TVDriver` class derived from the common API. Use a valid Python package name.
  For this rehearsal, retain the original Samsung files privately for rollback.
- [ ] Keep construction free of I/O; bound every operation and response size.
  Use private configuration for addresses, credentials and pins. Validate input
  identifiers and restrict commands to the intended operations.
- [ ] Keep retries, cancellation, setup qualification, idle behaviour and previous
  state restoration in `TVControl`. Use its existing per-operation callbacks and
  cancellation predicate. Recheck cancellation after blocking I/O and before sends.
- [ ] Add an explicit registry entry in `tv_plugins/__init__.py`; configuration must
  not import arbitrary module paths. Wire selection through the existing controller
  integration. The current runtime selects Samsung; a registry entry alone does
  not introduce model discovery or a user-selectable driver setting.
- [ ] If the TV needs an API or workflow change, stop and document that proposed
  extension, requirements impact and compatibility before expanding the contract.
  Do not silently add manufacturer-specific behaviour to the common UI.

## 6. Verify before replacing the working driver

Add direct LLT coverage under `tests/terminal/LLT/`, following existing
`test_tv_plugins.py`, `test_samsung_tv.py` and `test_tv_control.py` patterns.
Cover malformed/unavailable responses, timeouts, unsupported methods, certificate
changes, cancellation during authentication, repeated power requests and source
round trips. Assert that getters never infer state from a sent command and that
optional TV failures do not stop calling.

Maintain the required `@test`, `@requirements`, `@environment`, `@plan` and `@pass`
headers, reciprocal Doorstop references and owning `@llr` comments. Put physical
qualification plans in terminal HLT and record actual runs separately from plans.

Stage and test the candidate on the selected Pi during the agreed window:

| Scenario | Evidence required |
| --- | --- |
| TV in standby | Wake and show terminal; repeat on request does not turn it off |
| TV already displaying terminal | No unwanted power/input change |
| Live tuner or another HDMI source | Show terminal, then restore only a known, supported previous source |
| Smart-TV application | Correct supported behaviour or explicit unknown/unsupported result |
| Incoming call answered, declined, cancelled or unanswered | Correct existing controller restoration policy in each case |
| Terminal-initiated call and hang-up | Call picture/audio works; TV state restored according to policy |
| Remote input change during a call or restoration | No stale operation overrides a newer user/call action |
| Rapid call/end/new call | Earlier worker is cancelled; no delayed standby/input command |
| Network loss, revoked pairing or changed certificate | Bounded failure; normal calls remain usable |
| Long standby, TV/Pi reboot and HDMI socket move | Rediscovery/requalification where needed; no stale connector binding |
| Idle automation while another source is displayed | Other viewing is preserved; unknown visibility does not justify turning the TV off |

Use camera-only observation for standalone TV experiments. Stop that capture before
real call tests; inspect the call from the other endpoint instead. Record actual
answer-to-picture and command-to-visible-change timings rather than inventing
performance targets. Repeat critical cases at least three times for the prototype
and retain failures; this is a smoke test, not proof of long-term reliability.

### Repeatable plugin evidence bundle

During an idle maintenance window, run the generic developer self-test on the Pi:

```sh
sudo zmala-tv-test \
  --driver samsung --input 2.0.0.0 --input 0.0.0.0 \
  --delay 5 --operate-tv --pause-terminal \
  --output /var/tmp/tv-self-test.zip
```

The Pi terminal installer includes the internal `zmala-tv-test` command and all
its helpers. `sudo zmala-tv-test --help` lists the options without operating the TV.
The command follows `/opt/zmalacall/current`, including after upgrades or rollback.
It is not a startup service or a normal user settings action.

Replace the driver and input identifiers for the TV being investigated; those
values are plugin identifiers, not assumptions made by the runner. The example
uses a previously verified Samsung HDMI-2 binding and its tuner. `--config` can
select a private configuration file; `--cec-device` overrides automatic adapter
selection. The tool needs the deployed Pi runtime, OpenCV, camera access and
permission to pause/restart the terminal and wake the C20. Do not run during calls.

The standard sequence is:

1. Photograph the initial state.
2. Request off, then on, then on again, photographing and querying state at
   **5, 10 and 15 seconds after each command**, without intervening commands.
3. For each supplied input: select it, select it again, request standby, repeat
   standby, wake, then re-select the same input. Each action has the same three observations.
4. Exercise every directed pair of inputs (A → B and B → A for two inputs).
5. Attempt to restore the original input and power, with photos of restoration.

A fullscreen colour-bar card labelled **ZmalaCall TV TEST / TERMINAL HDMI INPUT**
with a live clock appears on the Pi's X display during the run. It makes the
terminal source recognisable and helps reveal frozen camera frames. The card
closes before the terminal service restarts. `--no-test-card` explicitly skips it
on systems without an X display. The Pi display service must already be running.

An unknown initial power state limits the run to observation. Unknown original
input is reported as incomplete source restoration. Unsupported methods are
recorded as skipped. Each operation runs in a separate process with a deadline,
followed by observations scheduled at three absolute offsets, each with a photo
then state queries. Actual capture start/completion times expose sampling overhead. The overview compares
reported state with requested state; this is separate from visual qualification.
The camera now stays open and drains frames continuously in a bounded child process.
It warms once before the initial observation; each snapshot requests the next
frame. Frame-read and save timings are recorded, rather than claiming an exact
sensor exposure timestamp. A stalled camera times out instead of reusing a stale
photo. The camera closes before normal terminal ownership resumes.

For a controlled settling comparison, run the same sequence separately with
`--observation-count 1 --delay 5`, then with delays 10 and 15. Keep the driver,
inputs and initial state identical. This takes one photo and queries power/input
per command; it does not wait for three samples. Actual inter-command gaps also
include photo and query overhead and are recorded explicitly. Compare pictures
against query answers, retain failed runs and repeat before attributing an
intermittent fault to timing. Queries themselves may affect the device, so this
is evidence for the tested polling pattern, not a proof of behaviour without it.
The report records command duration, not time to a visibly completed transition.

Retrieve the ZIP over the developer shell using an SSH binary stream (or SCP/SFTP
where configured). The restricted developer shell need not expose an SFTP
subsystem. Open `index.html` after extraction: photos are embedded, so this HTML
also works alone. `report.json` and individual JPEGs accompany it. The report
contains no configuration file, credential or raw third-party exception text;
photos can show private household content, so keep the bundle out of Git.
Existing ZIPs are never overwritten. Inspect every picture and result before
claiming physical qualification. Failed commands and missing photographs remain
visible evidence, even when the sequence reaches its end.

## 7. Deploy, document and close access

- [ ] Review the candidate diff and confirm private pairing files, images and
  hardware credentials are excluded. Update affected technical guides, user guides
  and requirements together; regenerate derived artifacts where affected.
- [ ] Run appropriate lint, LLT/HLT and `make requirements` after trace or test-plan
  changes. Report skipped/manual checks separately. Raise Android version name/code
  above current `main` for the PR, as required by repository release policy.
- [ ] Deploy with an exact revision, backup and verified rollback path. Preserve
  pairing data and ownership. Restart only the affected services while idle,
  then check registration, remote input and calls in both directions.
- [ ] Restore the previous driver/configuration if qualification fails. Record
  the limitation instead of marking the TV supported.
- [ ] Open the PR, wait for required Verify checks, resolve failures and merge
  through GitHub. Keep `W:\git\zmala` synchronized with the resulting `main`.
- [ ] Stop test previews, restore normal C20 ownership/power handling, leave the
  TV in the agreed state and disable developer access. Confirm tunnel closure.

**Deliverables:** a tested driver and registry integration, a model/firmware
support matrix with explicit limitations, private experiment evidence, synchronized
requirements/tests/documentation and a rollback record. A model name lookup or a
command returning success alone is not sufficient to declare the TV supported.

## Impact of this plan

This document describes investigation using the existing API and requirements;
it introduces no runtime behaviour or new product requirement. Existing code trace
comments and end-user guides remain accurate. The actual driver implementation is
a later change with its own impact review and physical verification evidence.


### Failure recovery and review boundaries

If the camera fails after the initial photograph, the runner stops the remaining
experimental commands, retains collected observations and attempts to restore
the original TV state. Restoration may have no photograph; inspect the report
rather than assuming it succeeded. Helper termination has deadlines, and cleanup
attempts to restart a previously active terminal even if a helper fails to exit
or the earlier stop command timed out. Cleanup failures produce a nonzero exit.
A terminal that was already stopped remains stopped.

The command runner, continuous camera child, process cleanup and HTML/ZIP report
have separate modules under `build_tools/linux/`. Development regressions use
fake processes and stateful TV fixtures in `tests/adhoc/test_tv_plugin_self_test.py`;
installer tests verify that every helper ships and `--help` runs from the package.
None of those local checks establish physical TV reliability. Preserve failed
hardware results and repeat the in-situ matrix separately when authorized.
