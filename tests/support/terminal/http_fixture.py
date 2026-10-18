"""Private HTTP test service, stopped and removed when the test leaves its context."""
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
from zmala_terminal.common.native_runtime import process_options
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]


@contextmanager
def http_server_fixture():
    with tempfile.TemporaryDirectory(prefix='provisioning-') as temporary:
        ready = Path(temporary) / 'ready'
        with (Path(temporary) / 'server.log').open('wb') as log:
            process = subprocess.Popen(
                ['node', str(ROOT / 'tests/support/server/http-live-server.js'), str(ready)],
                cwd=ROOT, stdin=subprocess.PIPE, stdout=log, stderr=log,
                **process_options(),
            )
            try:
                deadline = time.monotonic() + 10
                while not ready.exists():
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError('Isolated HTTP fixture did not start')
                    time.sleep(.05)
                directory = Path(ready.read_text(encoding='utf-8'))
                yield json.loads((directory / 'server.json').read_text(encoding='utf-8'))
            finally:
                process.stdin.close()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
