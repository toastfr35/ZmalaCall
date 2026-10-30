"""Best-effort Linux HDMI-CEC one-touch play, outside the SIP/Tk thread.

The connector's physical address identifies the input even after moving the Pi
to another HDMI port. Incoming calls retain the previous power/routing state;
rejecting or ending the call restores it outside the UI thread. Accepting a call
keeps the saved baseline until hang-up. Volume and mute are never controlled.
Windows and displays without CEC continue to work without TV control.
"""
import json
import logging
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time

from zmala_terminal.linux.tv_plugins import load_driver
from zmala_terminal.linux.cec_device import select_device


class TVControl:
    def __init__(self, device=None, state_file='/run/zmalacall-cec/state.json', driver='samsung'):
        self._automatic_device = device is None
        self.device = device or select_device()
        self.state_file = Path(state_file)
        self.command = shutil.which('cec-ctl') if sys.platform == 'linux' else None
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._closed = False
        self._ready = threading.Event()
        self._ready.set()
        self._started = None
        self._previous = None
        self._changed = False
        self._driver_name = driver
        self._driver_config_file = Path(__file__).resolve().parents[1] / 'data/tv-remote.json'
        self._network_enabled = True
        self._address = None
        self._input_pending = False
        self._browse_previous = None
        self._restore_pending = None
        self.power_enabled = True
        self.source_enabled = True

    def handle_button(self, on_visible, preserve_restore=False):
        """Consume a hidden-TV press; dispatch a visible-TV press asynchronously.

        Cached routing keeps normal navigation immediate. Unknown routing gets
        a fresh power/address check outside Tk; a press used to reveal the UI
        never also navigates, answers or hangs up. Further presses during HDMI
        settling are consumed, rather than queued as surprise actions.
        """
        self._refresh_device()
        if self._closed or not self.command or not Path(self.device).exists():
            return False
        if self._restore_pending is not None:
            # A fresh press supersedes idle restoration and only reveals the UI.
            self.wake(restore=preserve_restore)
            return True
        state = self._observed_state()
        if not self._control_allowed(state.get('off')):
            return False
        if (self._ready.is_set() and self._address is not None and
                state.get('off') is False and state.get('active_source') == self._address):
            return False
        if self._input_pending or not self._ready.is_set():
            return True
        self._input_pending = True
        token = self._cancel
        threading.Thread(target=self._button_worker,
                         args=(token, on_visible, preserve_restore, state), daemon=True,
                         name='zmala-cec-button').start()
        return True

    def _button_worker(self, token, on_visible, preserve_restore, observed=None):
        """Resolve the first press without blocking SIP or replacing a newer call."""
        observed = self._observed_state() if observed is None else observed
        try:
            with self._lock:
                if token is not self._cancel or self._closed:
                    return
                address = self._physical_address()
                if not address:
                    on_visible()  # Disconnected/non-CEC screens retain normal input.
                    return
                power = self._run('--to', '0', '--give-device-power-status')
                # Keep the state at the press. Samsung can change/report On
                # during visibility probing, before the wake worker captures it.
                off = observed.get('off')
                initial = {'off': off if isinstance(off, bool) else self._previous_power(power),
                           'source': self._previous_source(observed) or self._previous_source(), 'address': address}
                visible = initial['off'] is False and initial['source'] == address
            if token is not self._cancel or self._closed:
                return
            if visible or not self._control_allowed(initial['off']):
                on_visible()
            else:
                logging.info('CEC: button used to reveal terminal; action consumed')
                self.wake(restore=preserve_restore, initial=initial)
        except (OSError, subprocess.SubprocessError, RuntimeError):
            logging.warning('CEC: button visibility check failed; input continues', exc_info=True)
            if token is self._cancel and not self._closed:
                on_visible()
        finally:
            self._input_pending = False

    def pause_for_setup(self):
        """Invalidate normal wake/restore workers before the setup wizard owns CEC."""
        self._cancel.set()
        self._cancel = threading.Event()
        self._cancel.set()
        self._started = None

    # @llr LLR-TERM-TV-026
    def _control_allowed(self, off):
        if off is True:
            return self.power_enabled
        # After a restart the passive observer may know neither power nor input.
        # Qualified one-touch wake must still work when source switching was
        # skipped. Unknown power cannot authorize an unqualified power-on.
        return self.source_enabled if off is False else self.power_enabled

    def wake(self, restore=True, initial=None):
        self._refresh_device()
        if self._closed or not self.command or not Path(self.device).exists():
            return
        # A new call supersedes queued restoration, but inherits the original
        # baseline if the previous call ended before its worker could restore it.
        if restore and self._restore_pending is not None and self._browse_previous:
            # A call that interrupts idle restoration owns that original state.
            self._previous, self._browse_previous = self._browse_previous, None
            self._changed = True
        elif not restore and self._restore_pending is not None and self._browse_previous:
            # New identity restarts the countdown even if wake finishes between Tk ticks.
            self._browse_previous = dict(self._browse_previous)
        elif not restore:
            # A new reveal after the user changed TV input replaces the old lease.
            self._browse_previous = None
        self._restore_pending = None
        self._cancel.set()
        self._ready.clear()
        self._started = time.monotonic()
        cancel = self._cancel = threading.Event()
        threading.Thread(target=self._worker, args=(cancel, restore, initial), daemon=True,
                         name='zmala-cec').start()

    def cancel(self):
        self._cancel.set()
        self._ready.set()
        if self.command and self._started is not None:
            threading.Thread(target=self._restore, args=(self._cancel,), daemon=True,
                             name='zmala-cec-restore').start()

    def browsing_session(self):
        """Return the saved browsing lease only once HDMI switching has settled."""
        if not self._ready.is_set() or self._restore_pending is not None:
            return None
        previous = self._browse_previous
        if previous:
            state = self._observed_state()
            source = state.get('active_source')
            if state.get('off') is True or (source is not None and source != previous['address']):
                # The user selected another source/off themselves. Do not undo it.
                self._browse_previous = None
                return None
        return previous

    # @llr LLR-TERM-TV-028
    def restore_browsing(self, session):
        """End an idle browsing lease outside Tk; a new wake cancels stale commands."""
        if self._closed or session is None or session is not self._browse_previous:
            return
        self._cancel.set()
        cancel = self._cancel = threading.Event()
        self._restore_pending = cancel
        self._ready.clear()
        threading.Thread(target=self._restore, args=(cancel, True), daemon=True,
                         name='zmala-cec-idle-restore').start()

    def ready(self, now):
        """A failed/slow TV must never hold automatic answering indefinitely."""
        return self._ready.is_set() or self._started is None or now - self._started >= 30

    def close(self):
        self._closed = True
        self.cancel()

    # @llr LLR-TERM-TV-032
    # TV sequences use power/routing commands only; playback volume belongs to C20.
    def _run(self, *arguments):
        result = subprocess.run([self.command, '-d', self.device, '-s', *arguments],
                                capture_output=True, text=True, timeout=4, check=True)
        output = result.stdout + result.stderr
        # cec-ctl can exit successfully even when a CEC transmission fails.
        if re.search(r'transmit failed|tx, nack|tx, error', output, re.I):
            raise RuntimeError(output.strip())
        return output

    def _refresh_device(self):
        # Never redirect a saved TV restoration to another HDMI connector.
        if self._automatic_device and self.command and self._previous is None and self._browse_previous is None and self._ready.is_set():
            if not self._lock.acquire(blocking=False):
                return
            try:
                selected = select_device(self.device)
                if selected != self.device:
                    self.device = selected
                    self._address = None
            finally:
                self._lock.release()

    def _physical_address(self):
        address = self._run('--physical-address').strip().lower()
        if (re.fullmatch(r'[0-9a-f](\.[0-9a-f]){3}', address) and
                address not in ('f.f.f.f', '0.0.0.0')):
            self._address = address
            return address
        self._address = None
        return None

    def _worker(self, cancel, restore=True, initial=None):
        """Serialize CEC sequences; the per-call cancellation event prevents late source changes."""
        with self._lock:
            if cancel.is_set():
                return
            try:
                address = self._physical_address()
                if not address:
                    logging.warning('CEC: HDMI input address unavailable')
                    return
                if not restore:
                    # Browsing has its own lease, independent of call hang-up.
                    self._previous = None
                    self._changed = False
                previous = self._previous or (initial if initial and initial['address'] == address else None)
                if previous is None:
                    # Capture before configuring Playback: some TVs react to
                    # registration announcements by beginning to wake up.
                    try:
                        power = self._run('--to', '0', '--give-device-power-status')
                    except (OSError, subprocess.SubprocessError, RuntimeError):
                        power = ''  # An unknown state must not prevent ringing.
                    previous = {'off': self._previous_power(power),
                                'source': self._previous_source(), 'address': address}
                if not self._control_allowed(previous['off']):
                    return
                if restore:
                    self._previous = previous
                    logging.info('CEC: saved TV state off=%s, source=%s',
                                 previous['off'], previous['source'])
                # Already watching this terminal: leave the TV as it is,
                # without wake/source announcements or restoration commands.
                if previous['off'] is False and previous['source'] == address:
                    return
                if cancel.is_set():
                    return
                # Remember manual entry separately: hang-up must not expire its
                # idle timer. Unknown input/power cannot safely be restored.
                if not restore and self._browse_previous is None and (
                        previous['off'] is True or previous['source'] is not None):
                    self._browse_previous = previous
                    logging.info('CEC: saved browsing TV state off=%s, source=%s',
                                 previous['off'], previous['source'])
                # A command may take effect even if its reply times out.
                self._changed = restore
                # Reconfiguring a registered adapter can itself wake a TV.
                # Keep its logical identity and mark any first configuration as
                # a change that must be restored if cancellation races setup.
                logical = self._run('--logical-address').strip()
                if logical not in ('4', '8', '11'):
                    self._run('--playback', '--cec-version-1.4', '--osd-name', 'ZmalaCall')
                if cancel.is_set():
                    return
                if self.power_enabled:
                    self._run('--to', '0', '--image-view-on')
                # @llr LLR-TERM-TV-021
                # Power qualification does not authorize input switching. In
                # power-only mode leave source selection to the TV/user.
                if not self.source_enabled:
                    return
                if self.source_enabled and previous['off'] is False and previous['source'] == '0.0.0.0':
                    # Some Samsung tuners ignore CEC source selection while on.
                    # Use only the paired TV's explicitly verified source key,
                    # bound to this connector address; never guess/cycle inputs.
                    self._driver_call('set_current_input', address,
                                      is_current=lambda: cancel is self._cancel and not cancel.is_set())
                # Pairing/network I/O can race a cancelled or superseded call.
                if cancel.is_set():
                    return
                # A TV waking from standby may ignore the first announcement.
                # Retry only while this call remains active, never block the UI.
                awake_announcements = 0
                for delay in (0, 2, 3, 5, 5, 5):
                    if cancel.wait(delay):
                        return
                    self._run('--active-source', 'phys-addr=' + address)
                    # Power-on is not proof that the TV selected our input.
                    # Announce once more after settling, before allowing audio
                    # to start. Limit retries while awake: TVs may renegotiate
                    # HDMI audio whenever the source is announced.
                    power = self._run('--to', '0', '--give-device-power-status')
                    if re.search(r'pwr-state:\s*on\s*\(', power):
                        awake_announcements += 1
                        if awake_announcements < 2:
                            continue
                        # CEC acknowledgement precedes actual picture/sound.
                        if cancel.wait(2):
                            return
                        break
                logging.info('CEC: wake and HDMI input selection sent (%s)', address)
            except (OSError, subprocess.SubprocessError, RuntimeError):
                logging.warning('CEC: TV control failed; call continues', exc_info=True)
            finally:
                if cancel is self._cancel:
                    self._ready.set()

    def _observed_state(self):
        """An expired/dead observer cannot supply a remembered TV state."""
        try:
            value = json.loads(self.state_file.read_text(encoding='utf-8'))
            if not isinstance(value, dict):
                return {}
            if (value.get('device') == self.device and
                    0 <= time.time() - value['updated_at'] < 5):
                return value
        except (OSError, ValueError, TypeError, KeyError):
            pass
        return {}

    # @llr LLR-TERM-TV-027
    def _previous_power(self, output):
        match = re.search(r'pwr-state:\s*(on|standby|to-on|to-standby)\s*\(', output)
        if match and match[1] in ('on', 'standby'):
            return match[1] == 'standby'
        # Samsung can report to-on while physically off. A remembered Standby
        # or settled power report is stronger evidence than a transition reply.
        observed = self._observed_state().get('off')
        if isinstance(observed, bool):
            return observed
        return match[1] == 'to-standby' if match else None

    def _previous_source(self, observed=None):
        """Only a live observer may supply remembered routing; never guess HDMI 1."""
        source = (self._observed_state() if observed is None else observed).get('active_source')
        if (isinstance(source, str) and re.fullmatch(r'[0-9a-fA-F](\.[0-9a-fA-F]){3}', source)
                and source.lower() != 'f.f.f.f'):
            return source.lower()
        return None

    def _restore(self, cancel, browsing=False):
        """Serialize with wake; an older call must not put a newer call's TV to sleep."""
        with self._lock:
            if cancel is not self._cancel:
                return
            previous = self._browse_previous if browsing else self._previous
            if not previous:
                return
            try:
                if not browsing and not self._changed:
                    return
                if self.source_enabled and previous['source'] != previous['address']:
                    self._run('--to', '0', '--inactive-source', 'phys-addr=' + previous['address'])
                    if cancel is not self._cancel:
                        return
                    if previous['source'] and previous['source'] != '0.0.0.0':
                        self._run('--set-stream-path', 'phys-addr=' + previous['source'])
                        if cancel is not self._cancel:
                            return
                        # Samsung ignores Inactive Source/Set Stream Path from
                        # playback devices. Reannounce the remembered route as
                        # a compatibility fallback; no hard-coded input number.
                        self._run('--active-source', 'phys-addr=' + previous['source'])
                    elif previous['source'] == '0.0.0.0':
                        # Request a return to the TV's own source. Announcing
                        # the TV address from our playback device can leave
                        # Samsung displaying HDMI while reporting a TV route;
                        # reserve that fallback above for external sources.
                        if not self._restore_wait(2, cancel):
                            return
                        # Some Samsung TVs acknowledge CEC release but keep
                        # displaying HDMI. The explicitly paired network
                        # remote selects the tuner without changing channel.
                        if self._driver_call('set_current_input', '0.0.0.0',
                                             is_current=lambda: cancel is self._cancel):
                            if not self._restore_wait(3, cancel):
                                return
                    else:
                        logging.warning('CEC: previous input unknown; requested TV-native restoration')
                if cancel is not self._cancel:
                    return
                if self.power_enabled and previous['off'] is True:
                    # Restore the remembered input before standby too, so the
                    # TV next powers on to the same source as before the call.
                    if previous['source'] and previous['source'] != previous['address']:
                        if not self._restore_wait(2, cancel):
                            return
                    # An unanswered call may end while the TV is still booting.
                    # Such TVs can ignore Standby until wake-up has settled.
                    for delay in (0, 3, 5, 5):
                        if not self._restore_wait(delay, cancel):
                            return
                        self._run('--to', '0', '--standby')
                        power = self._run('--to', '0', '--give-device-power-status')
                        if re.search(r'pwr-state:\s*standby\s*\(', power):
                            break
                    # Samsung may ignore CEC Standby after returning to its
                    # tuner. Never toggle power based on transition/unknown
                    # replies: query again after network authentication, and
                    # send only if this call still owns restoration and the
                    # TV explicitly reports settled on.
                    if re.search(r'pwr-state:\s*on\s*\(', power):
                        self._driver_call('set_power_off', is_current=lambda: cancel is self._cancel)
                logging.info('CEC: previous TV state restoration sent')
            except (OSError, subprocess.SubprocessError, RuntimeError):
                logging.warning('CEC: TV restoration failed', exc_info=True)
            finally:
                if cancel is self._cancel:
                    if browsing:
                        self._browse_previous = None
                        self._restore_pending = None
                        self._ready.set()
                    else:
                        self._previous = None
                        self._changed = False

    # @llr LLR-TERM-TV-033
    def _driver_call(self, method, *args, is_current, trial_source=None):
        """Use the common API; capture cancellation per operation, never globally.

        CEC remains the primary transport. Model plugins supply the qualified
        network fallback. Setup and calls use the same driver and private file.
        """
        if not self._network_enabled or not is_current():
            return False
        try:
            driver = load_driver(self._driver_name, {
                'config_file': self._driver_config_file,
                'is_current': is_current,
                'read_power': self._driver_power_status,
                'read_input': self._previous_source,
                'power_on': self._driver_power_on,
                'trial_source': trial_source or {},
            })
            if method not in driver.get_capabilities():
                return False
            return getattr(driver, method)(*args)
        except Exception as error:
            # Driver errors may contain credentials. Calls must continue even
            # when an optional TV operation fails.
            logging.warning('TV: driver operation failed (%s)', type(error).__name__)
            return False

    def _driver_power_status(self):
        """Fresh, settled CEC status; transitions and failures remain unknown."""
        try:
            output = self._run('--to', '0', '--give-device-power-status')
            match = re.search(r'pwr-state:\s*(on|standby)\s*\(', output)
            return match[1] == 'on' if match else None
        except (OSError, subprocess.SubprocessError, RuntimeError):
            return None

    def _driver_power_on(self):
        self._run('--to', '0', '--image-view-on')
        return True

    def _restore_wait(self, seconds, cancel):
        """Allow firmware to settle, stopping promptly when another call arrives."""
        deadline = time.monotonic() + seconds
        while cancel is self._cancel:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            time.sleep(min(remaining, .1))
        return False
