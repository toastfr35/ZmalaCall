"""Bounded public release transport. No device credentials enter GitHub requests."""
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request
from urllib.parse import urlsplit
from zmala_terminal.linux.update_transaction import RecoveryError, sync_directory

API = 'https://api.github.com/repos/toastfr35/ZmalaCall/releases/latest'


def public_asset(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == 'https' and parsed.username is None and parsed.password is None
                and parsed.port in (None, 443) and not parsed.fragment
                and (parsed.hostname == 'release-assets.githubusercontent.com'
                     or parsed.hostname == 'github.com' and parsed.path.startswith('/toastfr35/ZmalaCall/releases/download/')))
    except (TypeError, ValueError):
        return False


class ReleaseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if req.full_url == API or not public_asset(newurl):
            raise RecoveryError('Unexpected release redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), ReleaseRedirect())


# @llr LLR-TERM-MAINT-030
def fetch(url, limit, transport=None):
    if url != API and not public_asset(url):
        raise RecoveryError('Untrusted release address')
    request = urllib.request.Request(url, headers={'User-Agent': 'ZmalaCall-terminal-updater', 'Accept': 'application/json'})
    with (transport or opener()).open(request, timeout=15) as response:
        if response.status != 200:
            raise RecoveryError('Release unavailable')
        data = response.read(limit + 1)
        if len(data) > limit:
            raise RecoveryError('Release response too large')
        return data


def latest_manifest(transport=None):
    release = json.loads(fetch(API, 1024*1024, transport))
    if release.get('draft') or release.get('prerelease'):
        return None
    assets = release.get('assets')
    if not isinstance(assets, list):
        raise RecoveryError('Invalid release metadata')
    matches = [entry for entry in assets if entry.get('name') == 'ZmalaTerminal-Update.json']
    if not matches:
        return None  # Earlier nine-download releases do not have an update feed.
    if len(matches) != 1:
        raise RecoveryError('Ambiguous update manifest')
    return fetch(matches[0]['browser_download_url'], 65536, transport)


# @llr LLR-TERM-MAINT-030
def download(manifest, cache, progress=lambda: None, transport=None):
    cache = Path(cache)
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    package = manifest['package']
    if not public_asset(package['url']):
        raise RecoveryError('Untrusted package address')
    target = cache / (package['sha256'] + '.tar.gz')
    if target.exists():
        from zmala_terminal.linux.update_package import verify_package
        try:
            verify_package(target, manifest)
            return target
        except RecoveryError:
            target.unlink()
    temporary = target.with_suffix('.part')
    request = urllib.request.Request(package['url'], headers={'User-Agent': 'ZmalaCall-terminal-updater'})
    digest, total, started = hashlib.sha256(), 0, time.monotonic()
    try:
        with (transport or opener()).open(request, timeout=15) as response, temporary.open('wb') as output:
            if response.status != 200:
                raise RecoveryError('Package unavailable')
            while True:
                if time.monotonic() - started > 600:
                    raise RecoveryError('Package transfer timed out')
                data = response.read(256*1024)
                if not data:
                    break
                total += len(data)
                if total > package['size']:
                    raise RecoveryError('Package larger than signed size')
                digest.update(data)
                output.write(data)
                progress()
            if total != package['size'] or digest.hexdigest() != package['sha256']:
                raise RecoveryError('Package integrity mismatch')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
        sync_directory(cache)
        return target
    finally:
        temporary.unlink(missing_ok=True)
