"""Persist unread contact counts without call or message contents."""
import json
import logging
from pathlib import Path
from zmala_terminal.common.json_storage import write_json


class MissedCallsStore:
    def __init__(self, path):
        self.path = Path(path)
        self.saved = None

    @staticmethod
    def account(config):
        return [config['sip']['domain'].lower(), config['sip']['username']]

    def load(self, config):
        return set(self.load_counts(config))

    def load_counts(self, config):
        """Bind badges to the SIP account and current contacts; migrate legacy contact-only entries to count one."""
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(value, dict) or value.get('account') != self.account(config):
                return {}
            contacts = value.get('contacts')
            if not isinstance(contacts, list) or len(contacts) > 40 or any(not isinstance(c, str) for c in contacts):
                return {}
            counts = value.get('counts', {})
            if not isinstance(counts, dict) or len(counts) > 40 or any(not isinstance(c, str) or type(n) is not int or n < 1 for c,n in counts.items()):
                return {}
            allowed = {c['id'] for c in config.get('contacts', []) if c['can_call']}
            return {c: counts.get(c, 1) for c in set(contacts) & allowed}
        except FileNotFoundError:
            return {}
        except (ValueError, OSError):
            logging.warning('Could not restore missed-call badges')
            return {}

    def save(self, config, contacts):
        counts = dict(contacts) if isinstance(contacts, dict) else {person: 1 for person in contacts}
        value = {'account': self.account(config), 'contacts': sorted(counts), 'counts': counts}
        if value == self.saved:
            return
        try:
            write_json(self.path, value)
            self.saved = value
        except OSError:
            logging.warning('Could not save missed-call badges')

    def clear(self):
        self.saved = None
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            logging.warning('Could not clear saved missed-call badges')
