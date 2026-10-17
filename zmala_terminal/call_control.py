"""Call and callback orchestration. Serial IDs keep late preflight responses from starting cancelled calls."""
import json
import logging
import threading
import time
from model import State


class CallControl:
    def registration_event(self, registered):
        self.last_registration = registered
        self.root.after_idle(self.render)

    def message_event(self, user, domain):
        config = self.model.config
        if self.setup_stage or not config or domain.lower() != config['sip']['domain'].lower():
            return
        if not any(c['id'] == user and c['can_receive'] for c in config['contacts']):
            return
        self.model.mark_notification(user)
        self.missed_calls_store.save(config, self.model.notifications)
        self.root.after_idle(self.render)

    def call_event(self, call, state, user, domain):
        """Map Liblinphone states to the model; ignore callbacks from an old or unaccepted call."""
        if state == 1:
            if self.setup_stage:
                self.engine.call_decline(call, 6)
                return
            if not self.model.incoming(user, domain):
                self.engine.call_decline(call, 6 if self.model.state != State.HOME else 2)
                return
            if getattr(self, 'settings_hold', None):
                self.settings_hold.clear()
                self.settings_open = False
            self.engine.hold_call(call)
            if getattr(self, 'tv_control', None):
                self.tv_control.wake()
            self.root.after_idle(lambda: self.root.lift())
            self.notice = ''
        elif state in (3, 4, 5, 6) and self.model.state == State.HOME:
            return
        elif call != self.engine.call:
            return
        elif state in (7, 8):
            if self.model.state == State.STOPPING:
                self.engine.end()
            else:
                if self.model.connected():
                    self.missed_calls_store.save(self.model.config, self.model.notifications)
                self.outgoing_deadline = None
        elif state in (13, 14, 19):
            failed = state == 13
            self.model.ended(remote=not failed)
            self.missed_calls_store.save(self.model.config, self.model.notifications)
            self.outgoing_deadline = None
            self.engine.hold_call(None)
            self.notice = 'unavailable' if failed else ''
            if getattr(self, 'tv_control', None):
                self.tv_control.cancel()
        self.root.after_idle(self.render)

    def show_callback_available(self, now):
        holding = getattr(self, 'settings_hold', None)
        if getattr(self, 'settings_open', False) or holding and holding.started is not None or self.setup_stage or self.model.state != State.HOME or now-self.last_button < 5 or self.callback_alert or self.notice or self.carousel_motion:
            return
        for request in reversed(self.callback_requests):
            if request['id'] in self.callback_seen or not request.get('ready'):
                continue
            own_id = self.model.config['sip']['username']
            person = request['to'] if request['from'] == own_id else request['from']
            index = next((i for i, c in enumerate(self.model.contacts) if c['id'] == person and self.contact_online(c)), None)
            if index is not None:
                self.callback_seen.add(request['id'])
                self.model.index = index
                self.callback_alert = (self.model.selected['name'], now+10)
                self.render()
                break

    def begin_callback(self, cancel=False):
        """Submit a request once; generation and serial checks guard its asynchronous result."""
        self.callback_serial += 1
        serial, generation = self.callback_serial, self.generation
        configuration, target = self.configuration, self.model.contact['id']
        request_id = self.model.callback_request['id'] if cancel else None
        own = self.model.config['sip']['username']
        def request_callback():
            reply = None
            try:
                if request_id:
                    reply = json.loads(configuration.request('/api/callbacks/' + request_id + '/cancel', {}))
                    success = reply.get('ok') is True
                else:
                    from config_validation import validate_callbacks
                    reply = json.loads(configuration.request('/api/callbacks', {'to': target}))
                    validate_callbacks([reply], own)
                    success = reply.get('to') == target and reply.get('from') == own
            except Exception:
                logging.warning('Callback request could not be confirmed')
                success = False
            self.messages.put(('callback-result', (generation, serial, target, success, reply, request_id)))
        threading.Thread(target=request_callback, daemon=True).start()

    def begin_dial(self):
        """Check current permission and presence before opening a native call."""
        self.notice = ''
        self.outgoing_deadline = time.monotonic() + 60
        self.dial_serial += 1
        serial, generation, contact = self.dial_serial, self.generation, dict(self.model.contact)
        configuration = self.configuration
        def check():
            try:
                reply = json.loads(configuration.request('/api/contacts/' + contact['id'] + '/availability'))
                available = reply.get('id') == contact['id'] and reply.get('online') is True and reply.get('can_call') is True
            except Exception:
                available = False
            timeout = reply.get('ring_timeout', 60) if available else 60
            timeout = timeout if type(timeout) is int and 60 <= timeout <= 660 else 60
            self.messages.put(('dial-ready', (generation, serial, contact, available, timeout)))
        threading.Thread(target=check, daemon=True).start()

    def answer_when_ready(self):
        """Wait for USB enumeration without blocking SIP iteration or answering an obsolete call."""
        ready = getattr(self, 'usb_media_ready', None)
        if ready and not ready():
            generation, call = self.generation, self.engine.call
            self.root.after(100, lambda: self.action('answer')
                if not self.closed and self.generation == generation and self.engine
                and self.engine.call == call and self.model.state == State.CONNECTING else None)
            return
        if getattr(self, 'usb_power', None):
            self.usb_power.stop_ringing()
        self.engine.answer()

    def action(self, action):
        if not action or (not self.engine and action not in ('request_callback', 'cancel_callback')):
            return
        try:
            if action in ('request_callback', 'cancel_callback'):
                self.begin_callback(cancel=action == 'cancel_callback')
            elif action == 'dial':
                self.begin_dial()
            elif action == 'answer':
                self.answer_when_ready()
            elif action in ('end', 'decline'):
                self.dial_serial += 1
                # Rejection ends the TV interruption immediately, even if the
                # SIP end callback arrives late. Answering retains the baseline.
                if action == 'decline' and getattr(self, 'tv_control', None):
                    self.tv_control.cancel()
                self.engine.end(decline=action == 'decline')
                if not self.engine.call:
                    self.model.ended()
                    self.outgoing_deadline = None
                    if action != 'decline' and getattr(self, 'tv_control', None):
                        self.tv_control.cancel()
        except Exception:
            logging.exception('Call action failed')
            if self.engine and self.engine.call:
                self.engine.end()
            self.model.ended()
            self.notice = 'unavailable'
            if getattr(self, 'tv_control', None):
                self.tv_control.cancel()

    def contact_online(self, contact):
        return bool(contact and contact.get('online') is True and time.monotonic() - self.server_seen < 6)

    def dial_ready(self, generation, serial, contact, available, ring_timeout=60):
        """A preflight reply may arrive after cancel/reset; verify both tokens before dialing."""
        if self.closed or self.setup_stage or generation != self.generation or serial != self.dial_serial or self.model.state != State.CALLING:
            return
        current = next((c for c in self.model.contacts if c['id'] == contact['id']), None)
        if not available or not current or not self.engine or not self.engine.registered:
            if current:
                current['online'] = False
            self.model.ended()
            self.outgoing_deadline = None
            self.notice = 'offline'
        else:
            try:
                ready = getattr(self, 'usb_media_ready', None)
                if ready and not ready():
                    self.root.after(100, lambda: self.dial_ready(generation, serial, contact, available, ring_timeout))
                    return
                self.outgoing_deadline = time.monotonic() + ring_timeout
                self.engine.dial(contact['sip_uri'])
            except Exception:
                logging.exception('Call could not be started')
                self.model.ended()
                self.outgoing_deadline = None
                self.notice = 'unavailable'
        self.render()
