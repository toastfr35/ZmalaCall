"""Keep idle C20 feedback warm; release its exclusive PCM before calls or tones."""
import logging
import os
import select
import subprocess
import threading
import time
from functools import lru_cache
from zmala_terminal.linux.sound_levels import click_pcm, playback_environment

PERIOD = .0025
FRAME = 480  # 2.5 milliseconds of stereo 16-bit PCM at 48 kHz.
SILENCE = bytes(FRAME)


# @llr LLR-TERM-AUDIO-010
@lru_cache(maxsize=1)
def click_bank():
    """About 3 MiB of ready-to-write PCM, retained across calls and volume changes.

    Build on the audio worker before opening ALSA. A press never synthesizes,
    scales, slices or reads a sound from disk, including its first use at a level.
    Zero is suppressed by play(); every other integer server/UI level is covered.
    """
    sounds = {}
    for percent in range(1,101):
        for button in ('left','green','red'):
            data = click_pcm(percent,button)
            sounds[percent,button] = tuple(data[i:i+FRAME].ljust(FRAME,b'\0')
                                          for i in range(0,len(data),FRAME))
    return sounds


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
        if button not in ('left','right','pointer','green','red'):
            raise ValueError('Unknown feedback button')
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
            sounds = click_bank()
            if self.stop.is_set():
                return  # Cancellation during preparation must not open the call's PCM.
            player = subprocess.Popen(['/usr/bin/aplay', '-q', '-D', 'default:C20',
                '-t', 'raw', '-f', 'S16_LE', '-c', '2', '-r', '48000',
                '--buffer-time=5000', '--period-time=2500', '--start-delay=1'],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=playback_environment(), bufsize=0, pipesize=4096)
            os.set_blocking(player.stdin.fileno(), False)
            with self.lock:
                self.player = player
            warmed_since = next_frame = time.monotonic()
            cue, position, started = (), 0, None
            while not self.stop.is_set():
                now = time.monotonic()
                with self.lock:
                    self.warmed = now-warmed_since >= .15
                    request, self.pending = self.pending, None
                    if request and now-request[1] <= .2 and not cue:
                        percent, queued, button, started = request
                        key = (percent, 'left' if button in ('left','right','pointer') else button)
                        cue = sounds[key]
                        position = 0
                    self.sounding = bool(cue)
                frame = cue[position] if cue else SILENCE
                if not self._write(player, frame):
                    break
                if cue:
                    position += 1
                    if position == len(cue):
                        cue = ()
                if started:
                    logging.debug('Button cue %s first frame after %.1f ms',
                                  button, (time.monotonic()-queued)*1000)
                    started.set()
                    started = None
                next_frame += PERIOD
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
                self.retry_at = 0 if self.stop.is_set() else time.monotonic()+1

    def cancel(self):
        deadline = time.monotonic()+.2
        with self.lock:
            self.enabled = self.warmed = False
            self.pending = None
            self.stop.set()
            player = self.player
            worker = self.worker
        self._stop_player(player)
        if worker and worker is not threading.current_thread():
            # Also cover cancellation while Popen is starting. Share the existing
            # stop budget; never wait indefinitely for a disconnected USB device.
            worker.join(timeout=max(0,deadline-time.monotonic()))

    def close(self):
        self.closed = True
        self.cancel()
