"""Resumable, user-confirmed installation TV checks, independent of Tk."""
import json
import logging
from pathlib import Path
import queue
import threading
import time

from zmala_terminal.linux.samsung_tv import save_config


class TVCheck:
    def __init__(self, path, transport):
        self.path, self.transport = Path(path), transport
        self.cancel = threading.Event()
        self.messages = queue.Queue()
        self.page = 'probe'
        self.record = {}
        self.error = False
        self.candidates = []
        self.selection = 0
        self.busy = False
        self.save_pending = None

    def launch(self, operation, *args):
        self.busy = True
        def worker():
            try:
                value = getattr(self.transport, operation)(self.cancel, *args)
                self.messages.put((operation, value, False))
            except Exception as error:
                logging.warning('TV installation %s failed (%s)', operation, type(error).__name__)
                self.messages.put((operation, None, True))
        threading.Thread(target=worker, daemon=True, name='zmala-tv-check').start()

    def start(self):
        self.launch('probe')

    def poll(self):
        if self.cancel.is_set():
            return False
        try:
            operation, value, error = self.messages.get_nowait()
        except queue.Empty:
            return False
        self.busy, self.error = False, error
        if operation == 'probe':
            try:
                saved = json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(saved, dict):
                    saved = {}
            except (OSError, ValueError):
                saved = {}
            valid = all(isinstance(saved.get(kind), dict) and saved[kind].get('status') in
                        ('pending', 'running', 'passed', 'failed', 'skipped') and
                        isinstance(saved[kind].get('attempts'), int) for kind in ('power', 'source'))
            # A standby/unplugged TV may temporarily have no EDID or CEC route.
            # That is not evidence of a new television. Keep completed checks
            # so restarting the terminal does not block SIP behind setup.
            same_tv = saved.get('identity') == value or (value is None and saved.get('complete') is True)
            self.record = saved if valid and saved.get('version') == 1 and same_tv and not error else {
                'version': 1, 'identity': value, 'power': {'status': 'pending', 'attempts': 0},
                'source': {'status': 'pending', 'attempts': 0}, 'complete': False}
            self.transport.resume_network(self.record.get('network_paired', False))
            if self.record.get('complete'):
                self.page = 'done'
            elif not value:
                self.page = 'unavailable'
            elif self.record['power']['status'] in ('passed', 'skipped') or self.record['power'].get('continued_without'):
                self.begin_source()
            else:
                self.page = 'power_ready'
        elif operation == 'power':
            self.page = 'power_confirm'
        elif operation == 'source':
            self.page = 'source_confirm' if value else 'source_timeout'
        elif operation == 'discover':
            self.candidates, self.selection = value or [], 0
            self.page = 'choose_tv' if self.candidates else 'no_tv'
        elif operation == 'pair':
            if error:
                self.page = 'retry_source'
            else:
                self.record['network_paired'] = True
                self.persist(lambda: self.set_page('paired'))
        return True

    def persist(self, next_action):
        try:
            save_config(self.path, self.record)
        except OSError:
            self.page, self.save_pending = 'save_error', next_action
            return
        self.save_pending = None
        next_action()

    def set_page(self, page):
        self.page = page

    def attempt(self, kind):
        entry = self.record[kind]
        entry.update(status='running', attempted_at=time.time(), attempts=entry['attempts']+1)
        def start():
            self.page = 'power_running' if kind == 'power' else 'source_wait'
            self.launch(kind)
        self.persist(start)

    def result(self, kind, passed):
        if kind == 'source' and passed:
            try:
                self.transport.confirm_source()
            except (OSError, ValueError):
                self.record[kind].update(status='failed', performed=True)
                self.persist(lambda: self.set_page('retry_source'))
                return
        self.record[kind].update(status='passed' if passed else 'failed', confirmed_at=time.time(), performed=True)
        self.persist(self.begin_source if kind == 'power' and passed else
                     self.finish if kind == 'source' and passed else
                     lambda: self.set_page('retry_power' if kind == 'power' else 'samsung'))

    def begin_source(self):
        self.page = 'source_ready'

    def finish(self):
        self.record.update(complete=True, completed_at=time.time())
        self.persist(lambda: self.set_page('summary'))

    def skip(self, kind):
        entry = self.record[kind]
        # Keep a failed/attempted result distinct from an unperformed skip.
        if entry['status'] not in ('failed', 'passed'):
            entry['status'] = 'skipped'
        entry.setdefault('performed', False)
        entry['continued_without'] = True
        self.persist(self.begin_source if kind == 'power' else self.finish)

    def button(self, button):
        if self.busy or button not in ('green', 'red', 'left', 'right'):
            return
        yes = button == 'green'
        if self.page == 'choose_tv' and button in ('left', 'right'):
            self.selection = (self.selection + (1 if button == 'right' else -1)) % len(self.candidates)
            return
        if button not in ('green', 'red'):
            return
        if self.page == 'power_ready':
            self.attempt('power') if yes else self.skip('power')
        elif self.page == 'power_confirm':
            self.result('power', yes)
        elif self.page == 'retry_power':
            self.attempt('power') if yes else self.skip('power')
        elif self.page in ('source_ready', 'retry_source', 'paired'):
            self.attempt('source') if yes else self.skip('source')
        elif self.page == 'source_confirm':
            self.result('source', yes)
        elif self.page == 'source_timeout':
            self.record['source'].update(status='failed', performed=False)
            self.persist(lambda: self.set_page('samsung'))
        elif self.page == 'samsung':
            self.page = 'samsung_help' if yes else 'sony'
        elif self.page == 'sony':
            self.page = 'sony_help' if yes else 'retry_source'
        elif self.page == 'sony_help':
            self.page = 'retry_source'
        elif self.page in ('samsung_help', 'no_tv'):
            if yes:
                self.page = 'discover'
                self.launch('discover')
            else:
                self.page = 'retry_source'
        elif self.page == 'choose_tv':
            if yes:
                self.page = 'pair'
                self.launch('pair', self.candidates[self.selection]['host'])
            else:
                self.page = 'retry_source'
        elif self.page == 'unavailable':
            if yes:
                self.page = 'probe'
                self.launch('probe')
            else:
                self.record['power'].update(status='skipped', performed=False)
                self.record['source'].update(status='skipped', performed=False)
                self.finish()
        elif self.page == 'save_error' and yes:
            self.persist(self.save_pending)
        elif self.page == 'summary' and yes:
            self.page = 'done'

    def close(self):
        self.cancel.set()
