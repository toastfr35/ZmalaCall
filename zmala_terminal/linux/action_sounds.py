"""Keep idle C20 feedback warm; release its exclusive PCM before calls or tones."""
import logging
import os
import select
import subprocess
import threading
import time
from zmala_terminal.linux.sound_levels import click_pcm, playback_environment

FRAME = 960  # Five milliseconds of stereo 16-bit PCM at 48 kHz.


# @llr LLR-TERM-AUDIO-010
class ActionSounds:
    def __init__(self):
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.pending, self.worker, self.player = None, None, None
        self.enabled = self.warmed = self.sounding = self.closed = False
        self.retry_at = 0

    def set_enabled(self, enabled):
        if not enabled:
            self.cancel()
            return
        with self.lock:
            self.enabled = not self.closed
            if self.enabled and self.worker is None and time.monotonic() >= self.retry_at:
                self.stop.clear()
                self.worker = threading.Thread(target=self.run, name='button-sound', daemon=True)
                self.worker.start()

    def play(self, percent, button='left'):
        if type(percent) is not int or not 0 <= percent <= 100:
            raise ValueError('Invalid button-sound volume')
        started = None
        with self.lock:
            if not percent:
                self.pending = None
            elif (not self.closed and self.enabled and self.warmed
                    and not self.sounding and self.pending is None):
                started = threading.Event()
                self.pending = (percent, time.monotonic(), button, started)
        if started and started.wait(.02):
            # Yield the GIL before Tk starts expensive portrait rendering. The first
            # PCM frame is already in the pipe; allow the small C20 buffer to drain
            # ahead of the visual action. Missing audio can delay input by at most
            # 20 ms, and a successful handoff by at most 40 ms in total.
            self.stop.wait(.02)

    def _write(self, player, data):
        """A tiny nonblocking pipe prevents queued audio or a stuck USB device hanging us."""
        deadline = time.monotonic()+.2
        view = memoryview(data)
        fd = player.stdin.fileno()
        while view and not self.stop.is_set():
            if time.monotonic() >= deadline:
                return False
            if not select.select([], [fd], [], .02)[1]:
                continue
            try:
                view = view[os.write(fd, view):]
            except BlockingIOError:
                continue
        return not view

    @staticmethod
    def _stop_player(player):
        if player is None:
            return
        try:
            if player.poll() is None:
                player.terminate()
            player.wait(timeout=.1)
        except subprocess.TimeoutExpired:
            player.kill()
            try:
                player.wait(timeout=.1)
            except subprocess.TimeoutExpired:
                logging.warning('C20 feedback player did not exit after termination')

    def run(self):
        player = None
        try:
            player = subprocess.Popen(['/usr/bin/aplay', '-q', '-D', 'default:C20',
                '-t', 'raw', '-f', 'S16_LE', '-c', '2', '-r', '48000',
                '--buffer-time=10000', '--period-time=5000', '--start-delay=1'],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=playback_environment(), bufsize=0, pipesize=4096)
            os.set_blocking(player.stdin.fileno(), False)
            with self.lock:
                self.player = player
            warmed_since = next_frame = time.monotonic()
            cue, sounds, started = b'', {}, None
            while not self.stop.is_set():
                now = time.monotonic()
                with self.lock:
                    self.warmed = now-warmed_since >= .15
                    request, self.pending = self.pending, None
                    if request and now-request[1] <= .2 and not cue:
                        percent, queued, button, started = request
                        key = (percent, 'left' if button in ('left','right','pointer') else button)
                        if key not in sounds:
                            sounds[key] = click_pcm(percent, button)
                        cue = sounds[key]
                    self.sounding = bool(cue)
                frame, cue = cue[:FRAME], cue[FRAME:]
                if not self._write(player, frame.ljust(FRAME, b'\0')):
                    break
                if started:
                    logging.debug('Button cue %s first frame after %.1f ms',
                                  button, (time.monotonic()-queued)*1000)
                    started.set()
                    started = None
                next_frame += .005
                if next_frame < time.monotonic()-.02:
                    next_frame = time.monotonic()  # Never stuff old frames to catch up.
                self.stop.wait(max(0, next_frame-time.monotonic()))
        except (OSError, ValueError):
            logging.debug('Button feedback unavailable', exc_info=True)
        finally:
            self._stop_player(player)
            if player and player.stdin:
                player.stdin.close()
            with self.lock:
                self.player = self.worker = self.pending = None
                self.warmed = self.sounding = False
                self.retry_at = time.monotonic()+1

    def cancel(self):
        with self.lock:
            self.enabled = self.warmed = False
            self.pending = None
            self.stop.set()
            player = self.player
        self._stop_player(player)

    def close(self):
        self.closed = True
        self.cancel()
