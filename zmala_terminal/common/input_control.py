"""Physical input dispatch, wake-only presses and carousel selection."""
import time
from zmala_terminal.common.carousel import CarouselMotion
from zmala_terminal.common.model import State
from zmala_terminal.linux.presenter_input import PresenterInput
from zmala_terminal.common.volume_control import VolumeControl


class InputControl:
    # @llr TLLR110
    def input_activity(self):
        """Wake USB before any TV routing, debounce or setup consumption."""
        self.last_button = time.monotonic()
        power = getattr(self, 'usb_power', None)
        if power:
            power.require(urgent=True)

    def bind_inputs(self):
        self.root.bind('<Configure>', self.resize)
        for key, button in [('Left', 'left'), ('Prior', 'left'), ('Right', 'right'), ('Next', 'right'), ('Return', 'green'), ('Escape', 'red')]:
            self.root.bind_all('<' + key + '>', lambda event, b=button: self.keypress(b))
            self.root.bind_all('<KeyRelease-' + key + '>', lambda event, b=button: self.queue_keyrelease(b))
        self.root.bind('<FocusOut>', lambda e: self.input_focus_lost())
        self.root.bind_all('<KeyPress>', self.other_key)
        self.root.bind('<F11>', self.toggle_fullscreen)
        self.volume_control = VolumeControl(self.root,
                                            lambda: bool(self.engine) and not self.setup_stage and not self.settings_open,
                                            self.volume_activity)
        self.presenter_input = PresenterInput(self.root, self.keypress, self.keyrelease,
                                               self.pointer_button, self.volume_control.motion,
                                               self.remote_test_event)

    def pointer_button(self, held):
        """Pointer follows the same wake-only first press as the other buttons."""
        self.input_activity()
        if self.setup_stage == 'tv' or self.remote_setup_blocked():
            return
        if held and 'pointer' in self.keys_down:
            return
        self.pointer_serial += 1
        if not held:
            self.keys_down.discard('pointer')
            self.volume_control.pointer(False)
            return
        self.keys_down.add('pointer')
        self.cancel_settings_hold()
        self.last_button = time.monotonic()
        generation, state, serial = self.generation, self.model.state, self.pointer_serial
        if not self.tv_control.handle_button(
                lambda: self.messages.put(('tv-pointer', (generation, state, serial))),
                preserve_restore=state in (State.RINGING, State.CONNECTING, State.IN_CALL)):
            self.volume_control.pointer(True)

    def pointer_visible(self, generation, state, serial):
        # A released/repressed pointer or a newly arrived call invalidates a
        # delayed visibility check; it must never start volume by itself.
        if (not self.closed and generation == self.generation and state == self.model.state
                and serial == self.pointer_serial and 'pointer' in self.keys_down):
            self.volume_control.pointer(True)

    def volume_activity(self):
        self.input_activity()

    def other_key(self, event):
        self.input_activity()
        self.cancel_settings_hold()
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

    # @llr TLLR093
    def keypress(self, button):
        self.input_activity()
        if self.remote_setup_blocked():
            return 'break'  # Keyboard/X11 copies must not pass the physical test.
        now = time.monotonic()
        # Repeated key-downs cannot restart a hold or repeat an action.
        release_job = self.key_release_jobs.pop(button, None)
        if release_job is not None:
            self.root.after_cancel(release_job)
        if button in self.keys_down:
            return 'break'
        self.keys_down.add(button)
        self.last_button = now  # Even a consumed/debounced press resets idle return.
        if self.tv_setup_button(button):
            return 'break'
        if now - self.last_key.get(button, 0) > .08:
            # Only physical input reveals the TV; timer-driven cancellation
            # still reaches press() directly. Workers return through Tk's queue.
            generation, state = self.generation, self.model.state
            if not self.tv_control.handle_button(
                    lambda: self.messages.put(('tv-button', (generation, state, button))),
                    preserve_restore=state in (State.RINGING, State.CONNECTING, State.IN_CALL)):
                self.press(button)
        self.last_key[button] = now
        return 'break'

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
        if moving and self.carousel_motion:
            return
        if moving:
            self.carousel_motion = CarouselMotion(list(self.model.contacts), self.model.index % len(self.model.contacts),
                                                  -1 if button == 'left' else 1, time.monotonic())
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
