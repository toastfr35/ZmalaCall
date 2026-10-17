"""Fetch pinned upstream Windows SDK packages into this project only."""
import bz2
import hashlib
import os
import runpy
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
runtime = ROOT / 'runtime'
runtime.mkdir(exist_ok=True)
PACKAGES = [
    ('linphone-sdk.zip', 'https://download.linphone.org/releases/windows/sdk/linphone-sdk-win64-5.4.98.zip',
     'fa6b899e0a1c6070911b45ef5a1664f8cc6563d7d89b507c15fa6b012062ea9f', 'linphone'),
    ('angle-desktop.zip', 'https://api.nuget.org/v3-flatcontainer/avalonia.angle.windows.natives/2.1.27548.20260419/avalonia.angle.windows.natives.2.1.27548.20260419.nupkg',
     '76d67901097e9173d155efc4c2b7d2c8e3122f2c2e0415028eb0c88478a386f9', 'angle-desktop'),
    ('openh264.bz2', 'https://ciscobinary.openh264.org/openh264-2.2.0-win64.dll.bz2',
     '799e08c418b6cdeadfbe18d027392158face4a5c901d41f83712a20f0d41ad7d', None),
]

def checksum(file):
    with file.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def package_file(filename, url, expected):
    """Interrupted downloads never replace a verified package in the local cache."""
    file = runtime / filename
    if not file.exists():
        print('Downloading', filename, flush=True)
        temporary = file.with_name(file.name + '.download')
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if checksum(temporary) != expected:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f'Checksum mismatch for {filename}; retry the download.')
        os.replace(temporary, file)
    if checksum(file) != expected:
        raise RuntimeError(f'Checksum mismatch for {filename}; remove the downloaded file and retry.')
    return file


for filename, url, expected, destination in PACKAGES:
    file = package_file(filename, url, expected)
    if destination:
        with zipfile.ZipFile(file) as archive:
            archive.extractall(runtime / destination)
    else:
        (runtime / 'linphone/linphone-sdk/win64/bin/openh264.dll').write_bytes(bz2.decompress(file.read_bytes()))
# Build adapters only after every upstream package has passed checksum verification.
runpy.run_path(str(ROOT / 'build-angle-forwarders.py'), run_name='__main__')
runpy.run_path(str(ROOT / 'build-qr-preview.py'), run_name='__main__')
runpy.run_path(str(ROOT / 'build-h264-decoder.py'), run_name='__main__')
print('Windows call runtime is ready.')
