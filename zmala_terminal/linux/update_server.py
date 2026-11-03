"""Read-only enrollment access for updater telemetry and the shared signed feed.

This transport never follows redirects or invokes configuration/media owners.
Device credentials are used only at the enrolled server, never at release CDNs.
"""
import json
import os
from pathlib import Path
import stat
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from zmala_terminal.linux.update_download import latest_manifest
from zmala_terminal.linux.update_transaction import RecoveryError


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# @llr LLR-TERM-MAINT-034
class ServerLink:
    def __init__(self, config, transport=None):
        self.bootstrap = Path(config.get('data', '/var/lib/zmalacall'))/'terminal.json'
        self.transport = transport or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def enrollment(self):
        provisioned = self.bootstrap.parent/'terminal/provisioning.json'
        try:
            descriptor = os.open(provisioned, os.O_RDONLY | os.O_NOFOLLOW)
            profile = True
        except FileNotFoundError:
            descriptor = os.open(self.bootstrap, os.O_RDONLY | os.O_NOFOLLOW)
            profile = False
        with os.fdopen(descriptor, 'r', encoding='utf-8') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_size > 16384:
                raise RecoveryError('Invalid updater enrollment')
            value = json.loads(stream.read(16385))
        if profile:
            if value.get('version') != 1 or not isinstance(value.get('bootstrap'), dict):
                raise RecoveryError('Terminal enrollment is not complete')
            value = value['bootstrap']
        url = urlsplit(value['server_url'])
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.path not in ('', '/') or url.query or url.fragment
                or url.hostname in ('github.com', 'api.github.com', 'release-assets.githubusercontent.com')
                or not isinstance(value['device_token'], str) or not 16 <= len(value['device_token']) <= 512
                or any(ord(character) < 33 or ord(character) > 126 for character in value['device_token'])):
            raise RecoveryError('Invalid enrolled update server')
        return value

    def request(self, route, data=None):
        enrollment = self.enrollment()
        headers = {'Authorization': 'Bearer '+enrollment['device_token']}
        if data is not None:
            data = json.dumps(data).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(enrollment['server_url'].rstrip('/')+route, headers=headers, data=data)
        with self.transport.open(request, timeout=4) as response:
            if response.status != 200:
                raise RecoveryError('Update server unavailable')
            body = response.read(131073)
            if len(body) > 131072:
                raise RecoveryError('Update server response too large')
            return json.loads(body)

    def manifest(self):
        try:
            value = self.request('/api/terminal-updates/manifest')['manifest']
            return None if value is None else json.dumps(value).encode()
        except FileNotFoundError:
            return latest_manifest()  # Unenrolled devices still stage public code quietly.
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return latest_manifest()  # Compatibility with earlier Pi servers.
            raise

    def report(self, phase, installed, available, error):
        self.request('/api/terminal-updates/status', {'phase': phase, 'installed': installed,
                                                    'available': available, 'error': error})
