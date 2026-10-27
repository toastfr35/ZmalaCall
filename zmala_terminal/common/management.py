"""UI-thread dispatch and timers. Workers never mutate Tk widgets or terminal state."""
import logging
import math
import queue
import threading
import time
from zmala_terminal.common.model import State
from zmala_terminal.common.peripherals import collect_peripheral_status
from zmala_terminal.common.connectivity import wifi_link_available

POLL_SECONDS = 2
PRESENCE_STALE_SECONDS = 6
TICK_MILLISECONDS = 20


def defer_auto_answer(model, tv, now):
    """Start the normal answer countdown after TV wake/HDMI settling.

    Manual answering remains immediate. TVControl bounds the extra wait, and
    deadline=None preserves manual-only accounts and red-button cancellation.
    """
    if model.state == State.RINGING and model.deadline is not None and tv and not tv.ready(now):
        model.deadline = max(model.deadline, now + model.config['auto_answer_seconds'])


class ManagementLoop:
    def usb_media_ready(self):
        power = getattr(self, 'usb_power', None)
        if not power or not power.enabled:
            return True
        power.require()
        power.refresh(self.engine)
        return power.ready

    # @llr LLR-TERM-POWER-013
    def tick_usb(self):
        power = getattr(self, 'usb_power', None)
        if power and power.enabled:
            active = bool(self.setup_stage or self.scanner or self.model.state != State.HOME
                          or self.engine and self.engine.call or self.settings_open
                          or getattr(self, 'keys_down', None))
            power.update(active, self.presenter_input.battery, self.model.state == State.RINGING)
            power.refresh(self.engine)

    def poll_wifi(self):
        """Refresh wireless status independently of setup and server availability."""
        if self.network_worker_busy:
            return
        self.network_worker_busy = True
        generation = self.generation

        def worker():
            try:
                available = wifi_link_available()
            except Exception:
                available = None
            self.messages.put(('poll-network', (generation, available)))
            self.messages.put(('network-done', None))
        threading.Thread(target=worker, daemon=True).start()

    def peripheral_status(self):
        return collect_peripheral_status(getattr(self, 'presenter_input', None),
            getattr(self, 'usb_power', None), getattr(self, 'c20_status', None))

    # @llr LLR-TERM-COM-007
    def poll(self):
        """Capture an enrollment generation before worker I/O; all results return through the UI queue."""
        self.poll_wifi()
        if self.worker_busy or not self.configuration or self.setup_stage:
            return
        self.worker_busy = True
        configuration, generation = self.configuration, self.generation
        callback_revision = getattr(self, 'callback_revision', 0)
        status = dict(self.diagnostics) | self.peripheral_status() | {
            'state': self.model.state.value,
            'configuration_version': self.model.config['configuration_version'] if self.model.config else 0,
        }

        def worker():
            try:
                self.messages.put(('poll-config', (generation, configuration.fetch(), callback_revision)))
                if not configuration.cancelled:
                    # @llr LLR-TERM-MAINT-018
                    configuration.report(status)
            except Exception as error:
                logging.warning('Management connection: %s', error)
            finally:
                self.messages.put(('poll-done', generation))
        threading.Thread(target=worker, daemon=True).start()

    def drain_messages(self):
        while True:
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                return
            self.handle_worker_message(kind, value)

    # @llr LLR-TERM-COM-008
    def handle_worker_message(self, kind, value):
        if kind == 'local-settings':
            self.local_settings_result(*value)
        elif kind == 'tv-pointer':
            self.pointer_visible(*value)
        elif kind == 'tv-button':
            generation, state, button = value
            # A delayed visibility query must not answer a newly arrived call
            # or act on an enrollment that has since been replaced.
            if not self.closed and generation == self.generation and state == self.model.state:
                self.physical_press(button)
        elif kind == 'dial-ready':
            self.dial_ready(*value)
        elif kind == 'callback-result':
            self.callback_result(*value)
        elif kind == 'setup':
            self.setup_result(*value)
        elif kind == 'poll-done':
            if value == self.generation:
                self.worker_busy = False
        elif kind == 'network-done':
            self.network_worker_busy = False
        elif kind in ('poll-config', 'poll-network'):
            generation, value, *revisions = value
            # Reset/re-enrollment invalidates every result from the old worker.
            if generation != self.generation:
                return
            if kind == 'poll-config' and not self.setup_stage:
                if revisions and revisions[0] != getattr(self, 'callback_revision', 0):
                    # A poll begun before a successful mutation cannot undo
                    # its tag change. The next fresh poll is authoritative.
                    value = dict(value, callbacks=self.callback_requests)
                self.apply_poll_config(value)
            elif kind == 'poll-network':
                self.network_connected = value
                self.draw_connectivity(bool(self.engine and self.engine.registered))

    # @llr LLR-TERM-HISTORY-023
    def callback_result(self, generation, serial, target, success, reply, request_id):
        if generation != self.generation or serial != self.callback_serial:
            return
        if success:
            self.callback_revision = getattr(self, 'callback_revision', 0) + 1
            removed = request_id or reply['id']
            self.callback_requests = [r for r in self.callback_requests if r['id'] != removed]
            if not request_id:
                self.callback_requests.append(reply)
            self.model.config['callbacks'] = list(self.callback_requests)
            if request_id:
                self.callback_alert = None
        if (self.model.state == State.REQUESTING_CALLBACK and self.model.contact
                and self.model.contact['id'] == target):
            self.model.ended()
            self.notice = ('' if request_id else 'callback_requested') if success else 'help'
            self.callback_notice_until = time.monotonic() + 4
            self.render()
        elif success and self.model.state == State.HOME:
            self.render()  # A request finishing after navigation still gets its tag.

    # @llr LLR-TERM-NAV-005
    def apply_poll_config(self, config):
        if self.model.config and config['configuration_version'] < self.model.config['configuration_version']:
            return
        self.server_seen = time.monotonic()
        changed = getattr(self, 'callback_requests', []) != config.get('callbacks', [])
        self.callback_requests = config.get('callbacks', [])
        # @llr LLR-TERM-COM-010
        # Hourly relay credentials change without an administrator's revision bump.
        # Route them through the normal idle/deferred engine replacement as well.
        if (not self.model.config or config['configuration_version'] != self.model.config['configuration_version']
                or config.get('secure_calls') != self.model.config.get('secure_calls')):
            self.apply_config(config)
            return
        # Reachability changes independently of the persisted configuration version.
        availability = {c['id']: c for c in config['contacts']}
        self.model.config['callbacks'] = list(self.callback_requests)
        for contact in self.model.config['contacts']:
            live = availability.get(contact['id'], {})
            online = live.get('online') is True
            presence = live.get('presence', 'available' if online else 'offline')
            previous_online = contact.get('online', False)
            previous_presence = contact.get('presence', 'available' if previous_online else 'offline')
            changed |= previous_online != online or previous_presence != presence
            contact.update(online=online, presence=presence)
        if changed and self.model.state == State.HOME:
            self.render()

    def update_timers(self, now):
        self.tick_settings_access(now)
        if self.pending_config and self.model.state == State.HOME and not self.setup_stage and now >= getattr(self, 'engine_retry_at', 0):
            config, self.pending_config = self.pending_config, None
            self.apply_config(config)
        if self.notice == 'callback_requested' and now >= self.callback_notice_until:
            self.notice = ''
            self.render()
        if self.callback_alert and now >= self.callback_alert[1]:
            self.callback_alert = None
            self.render()
        self.show_callback_available(now)
        stale = now - self.server_seen >= PRESENCE_STALE_SECONDS
        if stale != self.presence_stale:
            self.presence_stale = stale
            if self.model.state == State.HOME and not self.setup_stage:
                self.render()
        if now - self.last_poll > POLL_SECONDS:
            self.last_poll = now
            if self.engine:
                self.diagnostics = self.engine.diagnostics()
            self.poll()
        if self.outgoing_deadline and now >= self.outgoing_deadline and self.model.state in (State.CALLING, State.CONNECTING):
            self.press('red')
        if self.model.deadline:
            state = self.model.state
            power = getattr(self, 'usb_power', None)
            if state == State.RINGING and power and not power.ready:
                self.model.deadline = max(self.model.deadline, now + self.model.config['auto_answer_seconds'])
            defer_auto_answer(self.model, getattr(self, 'tv_control', None), now)
            self.action(self.model.tick(now))
            countdown = (self.model.state, max(1, math.ceil(self.model.deadline-now)) if self.model.deadline else None)
            if state != self.model.state or countdown != getattr(self, 'last_countdown', None):
                self.last_countdown = countdown
                self.render()

    def tick(self):
        """Pump native callbacks and queued results on Tk's thread before scheduling the next tick."""
        if self.closed:
            return
        try:
            self.tick_usb()
            if self.engine:
                self.engine.iterate()
            self.update_video_message()
            self.iterate_scanner()
            self.drain_messages()
            self.tick_ringtone(time.monotonic())
            self.tick_tv_setup()
            if self.configuration and self.configuration.photos.changed():
                if self.model.state == State.HOME:
                    self.render()
            now = time.monotonic()
            self.update_timers(now)
            self.update_setup_display(now)
            if self.carousel_motion:
                if self.model.state != State.HOME or self.carousel_motion.progress(now) >= 1:
                    self.carousel_motion = None
                self.draw_avatar(self.model.contact or self.model.selected)
            self.draw_connectivity(bool(self.engine and self.engine.registered))
            if self.model.state == State.RINGING:
                self.animate_ringing(now)
            self.tick_tv_idle(now)
            self.case_fan.update(self.model.state == State.IN_CALL)
        except Exception:
            logging.exception('Terminal tick failed')
            self.notice = 'help'
        # Match the kiosk's 60 Hz display during motion. Absolute deadlines
        # avoid drifting as frame rendering and Tk's timers take time.
        delay = self.carousel_motion.next_frame_delay(time.monotonic()) if self.carousel_motion else TICK_MILLISECONDS
        self.root.after(delay, self.tick)
