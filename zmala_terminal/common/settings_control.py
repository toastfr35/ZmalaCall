"""Local settings navigation and authenticated, acknowledged server updates."""
import threading
import time
from zmala_terminal.common.local_settings import SettingsDraft
from zmala_terminal.common.model import State


class SettingsControl:
    # @llr LLR-TERM-AUDIO-009
    def tick_ringtone(self, now):
        from zmala_terminal.common.ringtones import DEFAULT_SOUND, RingtoneCache
        configuration = getattr(self, 'configuration', None)
        cache = getattr(configuration, 'ringtones', None)
        cache = cache if isinstance(cache, RingtoneCache) else None
        power = self.usb_power
        config = self.model.config or {}
        selected = config.get('ringtone', 'nokia')
        file = cache.path(selected) if cache else DEFAULT_SOUND
        power.set_ringtone(file or DEFAULT_SOUND)
        if self.engine and not power.enabled and self.model.state == State.HOME:
            # Development/host policy without USB switching keeps SDK ringing.
            applied = str(file or DEFAULT_SOUND)
            key = (id(self.engine), applied)
            if key != getattr(self, 'sdk_ringtone_file', None):
                self.engine.core_set_ring(self.engine.core, applied.encode())
                self.sdk_ringtone_file = key
        draft = self.settings_draft
        editing = (self.settings_open and draft.editing and draft.key == 'ringtone' and
                   not draft.busy and self.model.state == State.HOME and not self.setup_stage)
        token = (self.generation, draft.options[draft.index]) if editing else None
        if token != getattr(self, 'ringtone_preview_token', None):
            power.stop_preview()
            self.ringtone_preview_token = token
            self.ringtone_preview_due = now+.4
            self.ringtone_preview_started = False
        state = ''
        if token:
            identity = token[1]
            if cache:
                cache.ensure(identity)
            preview = cache.path(identity) if cache else DEFAULT_SOUND if identity == 'nokia' else None
            if preview is None:
                state = 'error' if cache and cache.failed(identity) else 'waiting'
            elif now >= self.ringtone_preview_due:
                if not self.ringtone_preview_started:
                    power.preview_tone(preview)
                    self.ringtone_preview_started = True
                state = power.ringtone_preview_status
        if state != getattr(self, 'ringtone_preview_state', ''):
            self.ringtone_preview_state = state
            self.render()

    def tick_settings_access(self, now):
        hold = self.settings_hold
        if hold.started is None:
            return
        if self.setup_stage or self.model.state != State.HOME or not self.model.config:
            self.cancel_settings_hold()
        elif hold.update(now):
            hold.clear()
            self.settings_open = True
            self.settings_draft = SettingsDraft()
            self.carousel_motion = None
            self.callback_alert = None
            self.render()
        elif hold.capturing:
            self.carousel_motion = None
            self.render()

    def cancel_settings_hold(self):
        visible = self.settings_hold.capturing
        self.settings_hold.clear()
        if visible:
            self.render()

    def keyrelease(self, button):
        self.keys_down.discard(button)
        hold = self.settings_hold
        if button == 'red' and hold.started is not None:
            short = time.monotonic()-hold.started < 2
            self.cancel_settings_hold()
            if short and not self.settings_open and not self.setup_stage and self.model.state == State.HOME:
                self._press_action('red')

    def queue_keyrelease(self, button):
        # X11 keyboard auto-repeat emits a release/press pair. Defer release
        # until idle so its matching repeat can cancel it and preserve the hold.
        if button not in self.key_release_jobs:
            self.key_release_jobs[button] = self.root.after_idle(lambda: self.finish_keyrelease(button))

    def finish_keyrelease(self, button):
        self.key_release_jobs.pop(button, None)
        self.keyrelease(button)

    def input_focus_lost(self):
        self.keys_down.clear()
        self.cancel_settings_hold()
        # Focus changes can swallow a release. Stop motion and invalidate any
        # delayed visibility result so it cannot resume volume on its own.
        self.pointer_serial = getattr(self, 'pointer_serial', 0) + 1
        volume = getattr(self, 'volume_control', None)
        if volume:
            volume.pointer(False)

    def press(self, button):
        if self.setup_stage == 'tv' and self.tv_setup_button(button):
            return
        self.last_button = time.monotonic()
        if button != 'red':
            self.cancel_settings_hold()
        if self.settings_open:
            self.settings_button(button)
        elif (button == 'red' and button in self.keys_down and not self.setup_stage
              and self.model.config and self.model.state == State.HOME):
            # Defer only an idle physical red press. In-call red still acts
            # immediately, and timer/programmatic cancellations never hold.
            self.settings_hold.start(self.last_button)
        else:
            self._press_action(button)

    # @llr LLR-TERM-SETUP-032, LLR-TERM-CONFIG-019
    def settings_button(self, button):
        draft = self.settings_draft
        if draft.busy:
            return  # An accepted write may already have reached the server.
        if button in ('left', 'right'):
            draft.move(-1 if button == 'left' else 1)
        elif button == 'red':
            if draft.editing:
                draft.editing, draft.error = False, False
            else:
                self.settings_open = False
                self.settings_hold.clear()
        elif button == 'green':
            if draft.key == 'reset':
                self.settings_open = False
                self.setup_stage = 'reset'
                self.settings_hold.clear()
                self.carousel_motion = None
            elif draft.editing:
                self.save_local_setting()
            else:
                draft.open(self.model.config)
        self.render()

    def save_local_setting(self):
        draft = self.settings_draft
        changes = draft.change(self.model.config)
        if changes == draft.expected:
            draft.editing = False
            return
        configuration, generation = self.configuration, self.generation
        if not configuration:
            draft.error = True
            return
        draft.busy, draft.error = True, False
        expected = dict(draft.expected)

        def worker():
            config, success = None, False
            try:
                config = configuration.update_settings(changes, expected)
                success = True
            except Exception:
                # A timeout is ambiguous. Reconcile before offering a retry.
                try:
                    config = configuration.fetch()
                    success = all(config.get(key) == value for key, value in changes.items())
                except Exception:
                    pass
            self.messages.put(('local-settings', (generation, draft, success, config)))
        threading.Thread(target=worker, daemon=True).start()

    # @llr LLR-TERM-CONFIG-022
    def local_settings_result(self, generation, draft, success, config):
        if generation != self.generation or self.closed:
            return
        if config:
            self.apply_poll_config(config)
        draft.busy = False
        draft.error = not success
        if success:
            draft.editing = False
        elif config:
            # Older valid configurations can omit optional settings. Rebase
            # against the same defaults used when the editor was opened.
            draft.expected = draft.fields(config, draft.value(config, draft.key))
        self.render()
