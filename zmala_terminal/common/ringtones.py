"""Validated private ringtone downloads; the built-in tone remains available offline."""
from collections import deque
import hashlib
import os
from pathlib import Path
import re
import struct
import threading
import time
import uuid

DEFAULT_SOUND = Path(__file__).parent / 'assets/gentle-chime.wav'
MAX_SOUND = 44 + 16000*2*30
DEFAULT_CHOICES = [{'id': 'nokia', 'name': 'Nokia', 'url': '/api/ringtones/nokia.wav'}]


# @llr LLR-TERM-AUDIO-009
def validate_catalog(config):
    choices = config.get('ringtones', DEFAULT_CHOICES)
    if not isinstance(choices, list) or not 1 <= len(choices) <= 65:
        raise ValueError('Invalid ringtone list')
    seen = set()
    for item in choices:
        if not isinstance(item, dict):
            raise ValueError('Invalid ringtone')
        key = item.get('id')
        if not isinstance(key, str) or not re.fullmatch(r'nokia|[a-f0-9]{64}', key) or key in seen:
            raise ValueError('Invalid ringtone identity')
        if item.get('url') != f'/api/ringtones/{key}.wav':
            raise ValueError('Invalid ringtone path')
        name = item.get('name')
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in name):
            raise ValueError('Invalid ringtone name')
        seen.add(key)
    selected = config.get('ringtone', 'nokia')
    if 'nokia' not in seen or not isinstance(selected, str) or selected not in seen:
        raise ValueError('Choose an available ringtone')
    return choices


# @llr LLR-TERM-AUDIO-009
def valid_sound(data, identity):
    return (44 < len(data) <= MAX_SOUND and len(data) % 2 == 0 and
            data[:4] == b'RIFF' and data[8:36] == b'WAVEfmt '+struct.pack('<IHHIIHH', 16, 1, 1, 16000, 32000, 2, 16) and
            data[36:40] == b'data' and struct.unpack_from('<I', data, 4)[0] == len(data)-8 and
            struct.unpack_from('<I', data, 40)[0] == len(data)-44 and hashlib.sha256(data).hexdigest() == identity)


class RingtoneCache:
    def __init__(self, directory, request):
        self.directory, self.request = Path(directory), request
        self.lock = threading.RLock()
        self.catalog = {'nokia'}
        self.ready, self.pending, self.retry = set(), deque(), {}
        self.worker, self.cancelled = None, False

    # @llr LLR-TERM-AUDIO-009
    def configure(self, config):
        with self.lock:
            self.catalog = {item['id'] for item in validate_catalog(config)}
            self.ready.intersection_update(self.catalog)
        self.ensure(config.get('ringtone', 'nokia'))

    def path(self, identity):
        with self.lock:
            if identity == 'nokia':
                return DEFAULT_SOUND
            return self.directory / (identity+'.wav') if identity in self.ready else None

    def failed(self, identity):
        with self.lock:
            return identity in self.retry

    def ensure(self, identity):
        with self.lock:
            if (self.cancelled or identity == 'nokia' or identity not in self.catalog or identity in self.ready or
                    identity in self.pending or time.monotonic() < self.retry.get(identity, 0)):
                return
            self.pending.append(identity)
            if self.worker is None:
                self.worker = threading.Thread(target=self.run, name='ringtone-cache', daemon=True)
                self.worker.start()

    # @llr LLR-TERM-AUDIO-009
    def run(self):
        while True:
            with self.lock:
                if self.cancelled or not self.pending:
                    self.worker = None
                    return
                identity = self.pending[0]
            temporary = None
            try:
                file = self.directory / (identity+'.wav')
                try:
                    data = file.read_bytes() if file.stat().st_size <= MAX_SOUND else b''
                except OSError:
                    data = b''
                cached = valid_sound(data, identity)
                if not cached:
                    data = self.request(f'/api/ringtones/{identity}.wav')
                    if not valid_sound(data, identity):
                        raise ValueError('Invalid ringtone audio')
                with self.lock:
                    if self.cancelled or identity not in self.catalog:
                        continue
                    if not cached:
                        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                        self.directory.chmod(0o700)
                        temporary = self.directory / (uuid.uuid4().hex+'.tmp')
                        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as output:
                            output.write(data)
                        temporary.replace(file)
                    self.ready.add(identity)
                    self.retry.pop(identity, None)
            except (OSError, ValueError):
                with self.lock:
                    self.retry[identity] = time.monotonic()+30
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)
                with self.lock:
                    self.pending.popleft()

    def close(self):
        with self.lock:
            self.cancelled = True
