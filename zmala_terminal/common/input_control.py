"""Physical input dispatch, wake-only presses and carousel selection."""
import time
import logging
from zmala_terminal.common.carousel import CarouselMotion
from zmala_terminal.common.model import State
from zmala_terminal.linux.presenter_input import PresenterInput
from zmala_terminal.common.volume_control import VolumeControl


class InputControl:
    # @llr LLR-TERM-POWER-014
    def input_activity(self):
        """Wake USB before any TV routing, debounce or setup consumption."""
        self.last_button = time.monotonic()
        power = getattr(self, 'usb_power', None)
        if power:
            power.require(urgent=True)

    def bind_inputs(self):
        from zmala_terminal.linux.action_sounds import ActionSounds
        self.action_sounds = ActionSounds()
        self.root.bind('<Configure>', self.resize)
        for key, button in [('Left', 'left'), ('Prior', 'left'), ('Right', 'right'), ('Next', 'right'), ('Return', 'green'), ('Escape', 'red')]:
            self.root.bind_all('<' + key + '>', lambda event, b=button: self.keypress(b, event.time))
            self.root.bind_all('<KeyRelease-' + key + '>', lambda event, b=button: self.queue_keyrelease(b, event.time))
        self.root.bind('<FocusOut>', lambda e: self.input_focus_lost())
        self.root.bind_all('<KeyPress>', self.other_key)
        self.root.bind('<F11>', self.toggle_fullscreen)
        self.volume_control = VolumeControl(self.root,
                                            lambda: bool(self.engine) and not self.setup_stage and not self.settings_open,
                                            self.volume_activity,
                                            lambda: (self.generation, self.model.state, self.setup_stage, self.settings_open),
                                            in_call=lambda: self.model.state == State.IN_CALL)
        self.presenter_input = PresenterInput(self.root, self.keypress, self.keyrelease,
                                               self.pointer_button, None,
                                               self.remote_test_event)

    def pointer_button(self, held):
        """Pointer follows the same wake-only first press as the other buttons."""
        self.input_activity()
        if self.setup_stage == 'tv' or self.remote_setup_blocked():
            return
        if held and 'pointer' in self.keys_down:
            return
        if not held:
            self.keys_down.discard('pointer')
            self.volume_control.pointer(False)
            return
        self.pointer_serial += 1
        self.keys_down.add('pointer')
        InputControl.button_feedback(self, 'pointer')
        self.cancel_settings_hold()
        self.last_button = time.monotonic()
        generation, state, serial = self.generation, self.model.state, self.pointer_serial
        if not self.tv_control.handle_button(
                lambda: self.messages.put(('tv-pointer', (generation, state, serial))),
                preserve_restore=state in (State.RINGING, State.CONNECTING, State.IN_CALL)):
            self.volume_control.pointer(True)

    def pointer_visible(self, generation, state, serial):
        # A released click remains valid after a slow visibility check. A newer
        # click, call/state, focus change or enrollment invalidates the result.
        if (not self.closed and generation == self.generation and state == self.model.state
                and serial == self.pointer_serial):
            self.volume_control.pointer(True)
            if 'pointer' not in self.keys_down:
                self.volume_control.pointer(False)

    def volume_activity(self):
        self.input_activity()

    # @llr LLR-TERM-AUDIO-010
    def button_feedback(self, button='left'):
        player = getattr(self, 'action_sounds', None)
        power = getattr(self, 'usb_power', None)
        if player and power:
            logging.debug('Button feedback ready=%s state=%s call=%s ringing=%s preview=%s',
                power.ready, self.model.state, bool(self.engine and self.engine.call),
                power.ringing, power.ringtone_preview_status)
        if not player or not power or not power.ready:
            return  # Waking USB must not delay navigation or replay old clicks.
        if (self.model.state not in (State.HOME, State.CONFIRMING, State.CONFIRM_CALLBACK)
                or self.engine and self.engine.call
                or power.ringing or power.ringtone_preview_status in ('waiting', 'playing')):
            player.cancel()
            return
        if self.settings_open and self.settings_draft.editing and self.settings_draft.key in ('ringtone','ringtone_volume'):
            player.cancel()
            return
        config = self.model.config or {}
        draft = self.settings_draft
        percent = (draft.options[draft.index] if self.settings_open and draft.editing
                   and draft.key == 'action_sound_volume' else config.get('action_sound_volume', 20))
        player.play(percent, button)

    def other_key(self, event):
        self.input_activity()
        self.cancel_settings_hold()
        if self.volume_control.active is True:
            return 'break'
        if self.settings_open or self.settings_hold.capturing:
            return
        if self.model.state in (State.CONFIRMING, State.CONFIRM_CALLBACK, State.REQUESTING_CALLBACK):
            self.press('cancel')
            return 'break'

    def toggle_fullscreen(self, event):
        self.input_activity()
        if self.model.state in (State.CONFIRMING, State.CONFIRM_CALLBACK, State.REQUESTING_CALLBACK):
            self.press('cancel')
        else:
            self.root.attributes('-fullscreen', not self.root.attributes('-fullscreen'))
        return 'break'

    # @llr LLR-TERM-TV-026, LLR-TERM-NAV-004
    def keypress(self, button, event_time=None):
        self.input_activity()
        if self.remote_setup_blocked():
            return 'break'  # Keyboard/X11 copies must not pass the physical test.
        now = time.monotonic()
        # Repeated key-downs cannot restart a hold or repeat an action.
        release_job = self.key_release_jobs.pop(button, None)
        if release_job is not None:
            job, released_at = release_job
            self.root.after_cancel(job)
            # A busy canvas can leave a real release waiting for idle. X11
            # autorepeat pairs have equal event timestamps; a later arrow down
            # is a distinct click even if Tk has not run the release callback.
            if (button in ('left', 'right') and event_time is not None
                    and released_at is not None and event_time != released_at):
                self.keys_down.discard(button)
        if button in self.keys_down:
            return 'break'
        self.keys_down.add(button)
        InputControl.button_feedback(self, button)
        self.last_button = now  # Even a consumed/debounced press resets idle return.
        if self.tv_setup_button(button):
            return 'break'
        # Releases distinguish deliberate arrow clicks from held-key repeats.
        # Keep the confirmation debounce, but never discard a navigation click.
        if button in ('left', 'right') or now - self.last_key.get(button, 0) > .08:
            # Only physical input reveals the TV; timer-driven cancellation
            # still reaches press() directly. Workers return through Tk's queue.
            generation, state = self.generation, self.model.state
            if not self.tv_control.handle_button(
                    lambda: self.messages.put(('tv-button', (generation, state, button))),
                    preserve_restore=state in (State.RINGING, State.CONNECTING, State.IN_CALL)):
                self.physical_press(button)
        self.last_key[button] = now
        return 'break'

    # @llr LLR-TERM-REMOTE-016
    def physical_press(self, button):
        """Consume only user input in volume mode; internal call actions bypass it.

        Delayed TV visibility checks use this entry point too, so a queued remote
        press cannot dial behind a volume panel opened while that check was pending.
        """
        volume = getattr(self, 'volume_control', None)
        if volume and volume.active is True:
            self.cancel_settings_hold()
            volume.button(button)
        else:
            self.press(button)

    # @llr LLR-TERM-NAV-004
    def _press_action(self, button):
        self.last_button = time.monotonic()
        self.callback_alert = None
        if self.setup_stage:
            if self.setup_stage == 'reset' and button == 'red':
                self.setup_stage = None
                self.settings_open = True
                self.settings_hold.clear()
                self.render()
            elif self.setup_stage == 'reset' and button == 'green' and not self.setup_busy:
                self.factory_reset()
            return
        moving = self.model.state == State.HOME and button in ('left', 'right') and len(self.model.contacts) > 1
        if moving:
            direction = -1 if button == 'left' else 1
            if self.carousel_motion:
                self.carousel_motion.retarget(direction, time.monotonic())
            else:
                self.carousel_motion = CarouselMotion(list(self.model.contacts), self.model.index % len(self.model.contacts),
                                                      direction, time.monotonic())
        elif button in ('green', 'red'):
            self.carousel_motion = None
        confirming = self.model.state in (State.CONFIRMING, State.CONFIRM_CALLBACK)
        target = next((c for c in self.model.contacts if c['id'] == self.model.contact['id']), None) if confirming else self.model.selected
        unavailable = not self.contact_online(target) or confirming and not (self.engine and self.engine.registered)
        if button == 'green' and self.model.state == State.HOME and target and not self.contact_online(target):
            self.model.confirm_selected(False)
            self.missed_calls_store.save(self.model.config, self.model.notifications)
            self.render()
            return
        if button == 'green' and self.model.state == State.CONFIRMING and unavailable:
            if target:
                self.model.state = State.CONFIRM_CALLBACK
            else:
                self.model.ended()
                self.notice = 'unavailable'
            self.render()
            return
        action = self.model.button(button, bool(self.engine and self.engine.registered))
        if self.model.config:
            self.missed_calls_store.save(self.model.config, self.model.notifications)
        if self.model.state == State.HOME and button in ('left', 'right'):
            self.notice = ''
        self.action(action)
        self.render()
