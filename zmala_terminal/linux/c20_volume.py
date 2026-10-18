"""Set the C20's hardware playback level without touching HDMI or microphone gain."""
import logging
import subprocess
import threading

_condition = threading.Condition()
_desired = None
_applied = None
_worker = None
_configured = None
_failed = False


# @llr TLLR016
def configure(percent):
    """Keep local adjustments across core rebuilds; a changed server default wins."""
    global _configured
    if type(percent) is not int or not 0 <= percent <= 100:
        raise ValueError('C20 speaker volume must be 0–100 percent')
    with _condition:
        if _configured != percent:
            _configured = percent
            request(percent)
        elif _desired is not None:
            request(_desired)


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


# @llr TLLR015
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
        subprocess.run(['amixer', '-q', '-c', 'C20', 'sset', 'PCM', f'{percent}%'],
                       check=True, capture_output=True, timeout=5)
        logging.info('C20 speaker volume: %s%%', percent)
        return True
    except (OSError, subprocess.SubprocessError) as error:
        # A missing mixer must not prevent SIP registration or end a call.
        logging.warning('Could not set C20 speaker volume: %s', error)
        return False
