"""Call-volume state and fixed C20 output gain; individual streams attenuate independently."""
import logging
import subprocess
import threading
from zmala_terminal.linux.sound_levels import playback_environment

_condition = threading.Condition()
_desired = None
_applied = None
_worker = None
_configured = None
_default_revision = 0
_failed = False


# @llr LLR-TERM-AUDIO-008
def configure(percent):
    """Keep local adjustments across core rebuilds; a changed server default wins."""
    global _configured, _default_revision
    if type(percent) is not int or not 0 <= percent <= 100:
        raise ValueError('C20 speaker volume must be 0–100 percent')
    with _condition:
        if _configured != percent:
            _configured = percent
            _default_revision += 1
            request(percent)
        elif _desired is not None:
            request(_desired)


# @llr LLR-TERM-AUDIO-008
def default_revision():
    """Identify a changed saved default even when its value equals the current volume."""
    with _condition:
        return _default_revision


def status():
    with _condition:
        return _desired, _applied, _failed


def reapply():
    """A USB power cycle resets the hardware even if the desired level is unchanged."""
    global _applied
    with _condition:
        _applied = None
        if _desired is not None:
            request(_desired)


def request(percent):
    """Coalesce mixer changes on one worker, never blocking Liblinphone/Tk."""
    global _desired, _worker
    if type(percent) is not int or not 0 <= percent <= 100:
        raise ValueError('C20 speaker volume must be 0–100 percent')
    with _condition:
        _desired = percent
        if _worker is None and (percent != _applied or _failed):
            _worker = threading.Thread(target=_run, daemon=True)
            _worker.start()


# @llr LLR-TERM-AUDIO-007
def _run():
    global _worker, _applied, _failed
    while True:
        with _condition:
            percent = _desired
            if percent == _applied and not _failed:
                _worker = None
                return
        succeeded = apply(percent)
        with _condition:
            _failed = not succeeded
            if succeeded:
                _applied = percent
            elif percent == _desired:
                _worker = None
                return  # Retry only when requested again; no failure spin.


def apply(percent):
    if type(percent) is not int or not 0 <= percent <= 100:
        raise ValueError('C20 speaker volume must be 0–100 percent')
    try:
        # ALSA card identity survives USB re-enumeration. Do not pass "unmute":
        # changing the level must preserve any existing hardware mute state.
        # @llr LLR-TERM-AUDIO-010
        # A shared hardware gain would couple calls, ringtones and button sounds.
        # Keep it fixed; Engine applies the call-only gain on its owning thread.
        subprocess.run(['amixer', '-q', '-c', 'C20', 'sset', 'PCM', '100%'],
                       check=True, capture_output=True, timeout=5, env=playback_environment())
        logging.info('C20 output ready; call volume: %s%%', percent)
        return True
    except (OSError, subprocess.SubprocessError) as error:
        # A missing mixer must not prevent SIP registration or end a call.
        logging.warning('Could not set C20 speaker volume: %s', error)
        return False
