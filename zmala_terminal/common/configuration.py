"""Authenticated configuration retrieval and validated atomic local caching."""
import json
import logging
import sys
import copy
import threading
import urllib.request
from pathlib import Path
from zmala_terminal.common.config_validation import validate
from zmala_terminal.common.json_storage import write_json
from zmala_terminal.common.photo_cache import PhotoCache, MAX_BYTES, MAX_GIF_BYTES
from zmala_terminal.common.ringtones import RingtoneCache

from zmala_terminal.common.paths import ROOT as ROOT


# @llr LLR-TERM-COM-003
class NoCredentialRedirect(urllib.request.HTTPRedirectHandler):
    """An enrolled origin owns the bearer token; redirects cannot transfer it."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# @llr LLR-TERM-COM-006
def stable_configuration(config):
    """Offline snapshots retain settings, never live presence or callback state."""
    stable = copy.deepcopy(config)
    stable.pop('callbacks', None)
    stable.pop('developer_access', None)
    for contact in stable['contacts']:
        contact.pop('online', None)
        contact.pop('presence', None)
    return stable


class Configuration:
    def __init__(self, bootstrap=ROOT / 'data/terminal.json', cache=ROOT / 'data/config-cache.json'):
        self.bootstrap = dict(bootstrap) if isinstance(bootstrap, dict) else json.loads(Path(bootstrap).read_text(encoding='utf-8'))
        self.cache = Path(cache)
        self.lock = threading.Lock()
        self.fetch_lock = threading.Lock()
        self.cancelled = False
        self.current = None
        self.saved = None
        self.opener = urllib.request.build_opener(NoCredentialRedirect())
        self.photos = PhotoCache(ROOT / 'data', lambda route: self.request(route))
        self.ringtones = RingtoneCache(ROOT / 'data/ringtones', lambda route: self.request(route))

    def deactivate(self, erase=False):
        """Cancel writes under the same lock as persist, so a late poll cannot recreate an erased cache."""
        with self.lock:
            self.cancelled = True
            self.photos.close()
            self.ringtones.close()
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
        with self.opener.open(request, timeout=4) as response:
            limit = MAX_GIF_BYTES if route.startswith('/photos/') and route.endswith('.gif') else MAX_BYTES
            data = response.read(limit + 1)
            if len(data) > limit:
                raise ValueError('Response is too large')
            return data

    def update_settings(self, changes, expected):
        with self.fetch_lock:
            if self.cancelled:
                raise RuntimeError('Enrollment was reset')
            reply = json.loads(self.request('/api/device/settings', {'settings': changes, 'expected': expected}))
            return self.accept(reply, self.current or self.cached())

    def fetch(self, persist=True):
        with self.fetch_lock:
            return self._fetch(persist)

    def _fetch(self, persist=True):
        """Validate before caching; reject version rollback and treat missing contact photos as optional."""
        if self.cancelled:
            raise RuntimeError('Enrollment was reset')
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
            availability = {contact['id']: contact for contact in live['contacts']}
            for contact in config['contacts']:
                update = availability.get(contact['id'], {})
                contact['online'] = update.get('online', False)
                contact['presence'] = update.get('presence', 'available' if contact['online'] else 'offline')
            config['callbacks'] = live['callbacks']
            config['developer_access'] = live.get('developer_access')
        else:
            config = reply
        return self.accept(config, previous, persist)

    # @llr LLR-TERM-COM-006
    def accept(self, config, previous, persist=True):
        """Shared poll/write response boundary; callers hold fetch_lock."""
        config = validate(config, self.bootstrap['device_id'])
        if config.get('secure_calls') and not self.bootstrap['server_url'].startswith('https://'):
            raise ValueError('Secure-call enrollment requires HTTPS')
        if previous and previous['configuration_version'] > config['configuration_version']:
            raise ValueError('Refusing an older configuration')
        # @llr LLR-TERM-NET-009
        if persist and not self.cancelled and sys.platform == 'linux':
            from zmala_terminal.linux.developer_access import apply
            try:
                apply(config.get('developer_access'), self.bootstrap)
            except Exception:
                logging.warning('Developer access update failed; normal calls remain available')
        config.pop('developer_access', None)
        stable = stable_configuration(config)
        if persist:
            self.persist(stable)
        self.current = stable
        # Enrollment candidates do not start background work until committed.
        if persist:
            self.photos.schedule(config['contacts'])
            # @llr LLR-TERM-AUDIO-009
            self.ringtones.configure(config)
        return config

    def report(self, status):
        self.request('/api/status', status)
