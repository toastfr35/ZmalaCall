"""Keep native camera failures outside the terminal's Tk process."""
import json
import queue
import subprocess
import sys
import threading
from zmala_terminal.common.process_job import ProcessJob
from zmala_terminal.common.native_runtime import process_options
from zmala_terminal.common.runtime_logging import journal_logging

from zmala_terminal.common.paths import ROOT


class QRScanner:
    def __init__(self, on_qr, video_window=0, profile='terminal', camera=None, static_picture=None):
        self.on_qr, self.messages, self.closed = on_qr, queue.Queue(), False
        self.job = ProcessJob()
        self.error_log = None if journal_logging() else (ROOT / 'data' / 'qr-camera-error.log').open('ab', buffering=0)
        arguments = [sys.executable, '-m', 'zmala_terminal.common.qr_worker', '--window', str(video_window), '--profile', profile]
        if camera:
            arguments += ['--camera', camera]
        if static_picture:
            arguments += ['--image', str(static_picture)]
        try:
            self.process = subprocess.Popen(arguments, cwd=ROOT.parent, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=self.error_log, **process_options())
            self.job.assign(self.process)
            self.reader = threading.Thread(target=self.read_events, daemon=True)
            self.reader.start()
        except Exception:
            self.job.close()
            if getattr(self, 'process', None) and self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=5)
            if self.error_log:
                self.error_log.close()
            raise

    def read_events(self):
        # stdout is a private JSON-lines pipe. Native SDK diagnostics go to stderr.
        with self.process.stdout:
            for line in self.process.stdout:
                try:
                    event = json.loads(line)
                    if event.get('type') == 'qr' and isinstance(event.get('value'), str):
                        self.messages.put(event['value'])
                except (ValueError, TypeError):
                    pass

    def iterate(self):
        """Deliver worker events on the UI thread; reader threads only enqueue decoded text."""
        if self.closed:
            return
        if self.process.poll() is not None:
            location = 'journalctl -u zmalacall-terminal' if self.error_log is None else str(self.error_log.name)
            raise RuntimeError('Camera worker exited; see ' + location)
        while not self.messages.empty():
            self.on_qr(self.messages.get_nowait())

    def close(self):
        """Request graceful camera shutdown, then close the process job to reclaim remaining descendants."""
        if self.closed:
            return
        self.closed = True
        try:
            if self.process.poll() is None:
                try:
                    self.process.stdin.write(b'stop\n')
                    self.process.stdin.flush()
                    self.process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        finally:
            self.job.close()
            self.process.wait(timeout=5)
            self.process.stdin.close()
            self.reader.join(timeout=2)
            if self.error_log:
                self.error_log.close()
