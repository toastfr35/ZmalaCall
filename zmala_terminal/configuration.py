"""Authenticated configuration retrieval and validated atomic local caching."""
import json
import copy
import threading
import urllib.request
from pathlib import Path
from config_validation import validate
from json_storage import write_json
from photo_cache import PhotoCache, MAX_BYTES

ROOT = Path(__file__).resolve().parent


class Configuration:
    def __init__(self, bootstrap=ROOT / 'data/terminal.json', cache=ROOT / 'data/config-cache.json'):
        self.bootstrap = dict(bootstrap) if isinstance(bootstrap, dict) else json.loads(Path(bootstrap).read_text(encoding='utf-8'))
        self.cache = Path(cache)
        self.lock = threading.Lock()
        self.fetch_lock = threading.Lock()
        self.cancelled = False
        self.current = None
        self.saved = None
        self.photos = PhotoCache(ROOT / 'data', lambda route: self.request(route))

    def deactivate(self, erase=False):
        """Cancel writes under the same lock as persist, so a late poll cannot recreate an erased cache."""
        with self.lock:
            self.cancelled = True
            self.photos.close()
            if erase:
                self.cache.unlink(missing_ok=True)

    def persist(self, config):
        with self.lock:
            if self.cancelled:
                raise RuntimeError('Configuration was reset')
            if config != self.saved:
                write_json(self.cache, config)
                self.saved = copy.deepcopy(config)

    def cached(self):
        try:
            return validate(json.loads(self.cache.read_text(encoding='utf-8')), self.bootstrap['device_id'])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def request(self, route, data=None):
        headers = {'Authorization': 'Bearer ' + self.bootstrap['device_token']}
        if data is not None:
            data = json.dumps(data).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(self.bootstrap['server_url'] + route, headers=headers, data=data)
        with urllib.request.urlopen(request, timeout=4) as response:
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError('Response is too large')
            return data

    def update_settings(self, changes, expected):
        with self.fetch_lock:
            if self.cancelled:
                raise RuntimeError('Enrollment was reset')
            reply = json.loads(self.request('/api/device/settings', {'settings': changes, 'expected': expected}))
            reply = validate(reply, self.bootstrap['device_id'])
            stable = copy.deepcopy(reply)
            stable.pop('callbacks', None)
            for contact in stable['contacts']:
                contact.pop('online', None)
            self.persist(stable)
            self.current = stable
            return reply

    def fetch(self, persist=True):
        with self.fetch_lock:
            return self._fetch(persist)

    def _fetch(self, persist=True):
        """Validate before caching; reject version rollback and treat missing contact photos as optional."""
        previous = self.current or self.cached()
        route = '/api/config'
        if previous:
            route += '?delta=1&version=' + str(previous['configuration_version'])
        reply = json.loads(self.request(route))
        if isinstance(reply, dict) and 'live' in reply:
            if not previous or reply.get('configuration_version') != previous['configuration_version']:
                raise ValueError('Live update does not match cached configuration')
            config = copy.deepcopy(previous)
            live = reply['live']
            availability = {contact['id']: contact['online'] for contact in live['contacts']}
            for contact in config['contacts']:
                contact['online'] = availability.get(contact['id'], False)
            config['callbacks'] = live['callbacks']
        else:
            config = reply
        config = validate(config, self.bootstrap['device_id'])
        if previous and previous['configuration_version'] > config['configuration_version']:
            raise ValueError('Refusing an older configuration')
        # Presence is transient: keep it out of the durable offline cache.
        stable = copy.deepcopy(config)
        stable.pop('callbacks', None)
        for contact in stable['contacts']:
            contact.pop('online', None)
        if persist:
            self.persist(stable)
        self.current = stable
        # Enrollment candidates do not start background work until committed.
        if persist:
            self.photos.schedule(config['contacts'])
        return config

    def report(self, status):
        self.request('/api/status', status)
