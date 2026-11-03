"""Bounded local updater lease/heartbeat; never download or install from the UI."""
import json
import os
from pathlib import Path
import stat
import time
import uuid

REQUEST = Path('/run/zmalacall-updater/state.json')
STATUS = Path('/run/zmalacall/update.json')
PHASES = {'idle', 'request', 'updating', 'checking', 'rollback', 'recovery_failed'}


# @llr LLR-TERM-MAINT-028
class UpdateClient:
    def __init__(self, request=REQUEST, status=STATUS, clock=time.monotonic, root_uid=0):
        self.request = Path(request)
        self.status = Path(status)
        self.clock = clock
        self.root_uid = root_uid
        self.generation = uuid.uuid4().hex
        self.locked = False
        self.passive = False
        self.activated = False
        self.nonce = None
        self.next_tick = 0
        self.current = None
        self.refresh()

    def refresh(self):
        if os.name != 'posix':
            return None
        try:
            descriptor = os.open(self.request, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, 'r', encoding='utf-8') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != self.root_uid or info.st_mode & 0o022 or info.st_size > 8192:
                    return None
                request = json.loads(stream.read(8193))
            age = self.clock() - request['heartbeat']
            if (not 0 <= age <= 10 or request['phase'] not in PHASES
                    or not isinstance(request['nonce'], str) or len(request['nonce']) != 32):
                return None
        except (OSError, ValueError, TypeError, KeyError):
            return None
        self.current = request
        if request['nonce'] != self.nonce:
            self.nonce = request['nonce']
            # Genuine activity belongs to this app process, not the updater's
            # nonce. A restarted producer must not reapply an old sleep hint.
        if request['phase'] in ('updating', 'checking', 'rollback', 'recovery_failed'):
            self.locked = True
        elif request['phase'] == 'idle':
            self.locked = False
        if request.get('preserve_sleep') is True and not self.activated:
            self.passive = True
        return request

    def activity(self):
        if not self.locked:
            self.activated = True
            self.passive = False

    def tick(self, eligible, language, ready, sleeping, on_fence=None):
        now = self.clock()
        if now < self.next_tick:
            return
        self.next_tick = now + 1
        request = self.refresh()
        if request is None:
            if self.current and self.current['phase'] == 'request' and now - self.current['heartbeat'] > 10:
                self.locked = False
            return
        if request['phase'] == 'request' and eligible:
            if on_fence:
                on_fence()
            self.locked = True  # Fenced before acknowledging to the root updater.
        self.status.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.status.with_suffix('.next')
        value = {'nonce': self.nonce, 'generation': self.generation, 'pid': os.getpid(),
                 'heartbeat': now, 'ready': bool(ready), 'maintenance': self.locked,
                 'eligible': bool(eligible), 'language': language, 'sleeping': bool(sleeping)}
        temporary.write_text(json.dumps(value), encoding='utf-8')
        temporary.chmod(0o600)
        os.replace(temporary, self.status)


def tick_terminal(app, now):
    client = getattr(app, 'update_client', None)
    if client is None:
        return
    from zmala_terminal.common.model import State
    power = getattr(app, 'usb_power', None)
    maintenance = getattr(app, 'maintenance', None)
    television = getattr(app, 'tv_control', None)
    viewing = getattr(television, 'session', None)
    idle = (app.model.state == State.HOME and not (app.engine and app.engine.call)
            and not app.setup_stage and not app.settings_open and not app.setup_busy
            and not app.settings_draft.busy and not app.keys_down
            and not getattr(app, 'worker_busy', False)
            and not getattr(app, 'network_worker_busy', False)
            and not getattr(maintenance, 'busy', False)
            and not getattr(viewing, 'browsing', None)
            and not getattr(viewing, 'previous', None)
            and (getattr(power, 'deferred', False)
                 or getattr(power, 'state', None) not in ('switching', 'starting'))
            and now - app.last_button >= 120)
    def fence():
        hold = getattr(power, 'hold_for_update', None)
        if hold:
            hold()
        if maintenance:
            maintenance.stop()
            app.maintenance = None
        hold_tv = getattr(television, 'hold_for_update', None)
        if hold_tv:
            hold_tv()
    client.tick(idle, app.language, not app.closed,
                bool(client.passive or power and power.enabled and power.powered is False),
                on_fence=fence)
