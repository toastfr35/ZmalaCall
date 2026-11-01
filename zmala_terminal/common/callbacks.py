"""Callback state and HTTP work, independent of terminal views and call engines.

Only the UI thread changes this controller. Workers receive captured values and
post results to a queue; they never retain a terminal or update controller state.
"""
import json
import logging
import threading
from typing import NamedTuple
from zmala_terminal.common.config_validation import validate_callbacks


class CallbackResult(NamedTuple):
    generation: int
    serial: int
    target: str
    success: bool
    reply: dict | None
    request_id: str | None


class CallbackController:
    def __init__(self):
        self.requests = []
        self.seen = set()
        self.serial = 0
        self.revision = 0

    def reset(self):
        """Invalidate outstanding requests before changing enrollment."""
        self.requests = []
        self.seen.clear()
        self.serial += 1
        self.revision += 1

    # @llr LLR-TERM-HISTORY-021
    def submit(self, configuration, messages, generation, target, own, request_id=None):
        self.serial += 1
        serial = self.serial
        def worker():
            reply = None
            try:
                if request_id:
                    reply = json.loads(configuration.request('/api/callbacks/' + request_id + '/cancel', {}))
                    success = reply.get('ok') is True
                else:
                    reply = json.loads(configuration.request('/api/callbacks', {'to': target}))
                    validate_callbacks([reply], own)
                    success = reply.get('to') == target and reply.get('from') == own
            except Exception:
                logging.warning('Callback request could not be confirmed')
                success = False
            messages.put(('callback-result', CallbackResult(generation, serial, target, success, reply, request_id)))
        threading.Thread(target=worker, daemon=True).start()

    # @llr LLR-TERM-HISTORY-023
    def acknowledge(self, generation, result):
        """Return False for obsolete work, retaining tags until acknowledged."""
        if result.generation != generation or result.serial != self.serial:
            return False
        if result.success:
            self.revision += 1
            removed = result.request_id or result.reply['id']
            self.requests = [r for r in self.requests if r['id'] != removed]
            if not result.request_id:
                self.requests.append(result.reply)
        return True

    # @llr LLR-TERM-HISTORY-023
    def reconcile_poll(self, config, revision):
        """An older poll must not undo a successful create or cancellation."""
        return dict(config, callbacks=list(self.requests)) if revision != self.revision else config

    # @llr LLR-TERM-HISTORY-024
    def available(self, own, contacts, online):
        """Select a ready contact once, leaving navigation/rendering to the UI."""
        for request in reversed(self.requests):
            if request['id'] in self.seen or not request.get('ready'):
                continue
            person = request['to'] if request['from'] == own else request['from']
            index = next((i for i, c in enumerate(contacts) if c['id'] == person and online(c)), None)
            if index is not None:
                self.seen.add(request['id'])
                return index
        return None
