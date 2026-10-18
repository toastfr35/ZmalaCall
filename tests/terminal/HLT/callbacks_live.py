# @test T-HLT-003
# @requirements HLR-TERM-HISTORY-002
# @environment hardware
# @plan Run an isolated SIP/HTTP server with real terminal and phone peers; create and cancel callback requests and assert delivery, badges and notification behavior.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Real callback notifications, manual calls and incoming missed-call badges."""
import ctypes as C
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = (Path(__file__).resolve().parents[3] / 'zmala_terminal')
PROJECT = ROOT.parent
sys.path.insert(0, str(ROOT.parent))
from zmala_terminal.common.native_runtime import process_options
from zmala_terminal.common.main import Terminal
from zmala_terminal.common.engine import Engine, P, S, I, SDK, encoded
from zmala_terminal.common.model import State

directory = Path(tempfile.mkdtemp(prefix='callback-live-', dir=PROJECT/'build_tools/tmp'))
logging.basicConfig(filename=directory/'terminal.log', level=logging.INFO)
test_profile = 'callbacks-'+directory.name.removeprefix('callback-live-')
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
    probe.bind(('127.0.0.1', 0))
    sip_port = probe.getsockname()[1]
log = (directory/'server.log').open('w')
server = subprocess.Popen(['node', str(PROJECT/'tests/support/server/callbacks-live-server.js'), str(directory), str(sip_port)],
                          stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, **process_options(),
                          env=dict(os.environ, VIDEOCALL_DEBUG='1'))
app, phone = None, None
received, calls = [], []
iterate_phone = True
try:
    deadline = time.monotonic()+10
    while not (directory/'ready').exists() and time.monotonic()<deadline:
        assert server.poll() is None, 'Isolated server failed to start'
        time.sleep(.1)
    assert (directory/'ready').exists(), 'Isolated server startup timed out'
    settings = json.loads((directory/'server.json').read_text())
    base = f"http://127.0.0.1:{settings['http_port']}"
    def api(route, method='GET', value=None):
        request = urllib.request.Request(base+route, method=method, headers={'Authorization':'Bearer '+settings['admin_token'], 'Content-Type':'application/json'}, data=None if value is None else json.dumps(value).encode())
        with urllib.request.urlopen(request, timeout=4) as response:
            return json.load(response)
    app = Terminal(bootstrap=directory/'terminal.json', profile=test_profile)
    def pump(predicate, seconds=8):
        limit = time.monotonic()+seconds
        while time.monotonic()<limit:
            app.root.update()
            if phone and iterate_phone:
                phone.iterate()
                if calls:
                    calls.clear()
                    phone.answer()
            if predicate():
                return
            time.sleep(.02)
        raise AssertionError(f'Callback scenario timed out: terminal={app.model.state}, terminal_call={app.engine.call if app.engine else None}, phone_call={phone.call if phone else None}, missed={app.model.missed_calls}; logs in {directory}')
    pump(lambda: app.engine and app.engine.registered and app.model.contacts)
    if '--debug' in sys.argv:
        library = app.engine.dll
        service = library.linphone_logging_service_get
        service.argtypes, service.restype = [], P
        log_file = library.linphone_logging_service_set_log_file
        log_file.argtypes, log_file.restype = [P,S,S,C.c_size_t], None
        log_level = library.linphone_logging_service_set_log_level_mask
        log_level.argtypes, log_level.restype = [P,C.c_uint], None
        log_file(service(), encoded(directory), b'native.log', 5000000)
        log_level(service(), 63)
    assert app.model.selected['id']=='phone1' and not app.model.selected['online']
    app.press('green')
    assert app.model.state == State.CONFIRM_CALLBACK
    assert app.confirmation_question == 'Do you want to request a callback?'
    app.press('red')
    assert app.model.state == State.HOME and not api('/api/admin')['callbacks']
    app.press('green');app.press('green')
    pump(lambda: app.model.state == State.HOME and app.notice == 'callback_requested')
    request = api('/api/admin')['callbacks'][0]
    assert request['from']=='term1' and request['to']=='phone1' and request['notified_at'] is None
    assert app.engine.call is None, 'Callback request started a call'
    assert app.model.pending_callback(app.model.selected)['id'] == request['id']
    assert app.avatar.find_withtag('callback-pending-phone1'), 'Pending callback has no contact tag'
    app.press('red')
    assert app.model.state == State.CONFIRM_CALLBACK and app.model.callback_request['id'] == request['id']
    assert app.confirmation_question == 'Cancel ?'
    app.press('red')
    assert api('/api/admin')['callbacks'][0]['status'] == 'pending', 'No cancelled the request'
    app.press('red'); app.press('green')
    pump(lambda: app.model.state == State.HOME and not app.model.pending_callback(app.model.selected))
    assert api('/api/admin')['callbacks'][0]['status'] == 'cancelled'
    assert not app.avatar.find_withtag('callback-pending'), 'Cancelled callback tag remains visible'
    # Recreate for notification/completion coverage below.
    app.press('green'); app.press('green')
    pump(lambda: app.model.state == State.HOME and app.notice == 'callback_requested')
    request = api('/api/admin')['callbacks'][0]
    config = app.configuration.fetch()
    config['sip'].update(username='phone1', password=settings['users']['phone1']['password'])
    config['account_type'] = 'linphone'
    def incoming(call, state, *_):
        if state == 1:
            phone.hold_call(call);calls.append(call)
        elif state in (14,19) and call == phone.call:
            phone.hold_call(None)
    phone = Engine(config, incoming, lambda *_: None, profile=test_profile+'-phone')
    MSG_CB = C.CFUNCTYPE(None, P, P, P)
    text = phone.dll.linphone_chat_message_get_utf8_text
    text.argtypes, text.restype = [P], S
    message_callback = MSG_CB(lambda core, room, msg: received.append((text(msg) or b'').decode('utf-8')))
    setter = phone.dll.linphone_core_cbs_set_message_received
    setter.argtypes, setter.restype = [P, MSG_CB], None
    cbs = phone.factory_create_core_cbs(phone.factory)
    setter(cbs, message_callback);phone.core_add_callbacks(phone.core,cbs);phone.core_cbs_unref(cbs)
    pump(lambda: bool(received), 12)
    assert len(received)==1 and 'Evelyn' in received[0] and 'sip:term1@127.0.0.1' in received[0], received
    pump(lambda: bool(api('/api/admin')['callbacks'][0]['notified_at']))
    app.last_button = time.monotonic()-10
    pump(lambda: app.callback_alert is not None)
    assert app.model.state == State.HOME and app.engine.call is None
    app.press('green')
    assert app.model.state == State.CONFIRMING and app.confirmation_question == 'Do you want to call Noah?'
    # Avoid capturing room audio on either endpoint.
    for engine in [app.engine, phone]:
        for name, types, values in [('core_set_use_files',[P,I],[engine.core,1]),('core_set_play_file',[P,S],[engine.core,encoded(SDK/'share/sounds/linphone/hello8000.wav')])]:
            function=getattr(engine.dll,'linphone_'+name);function.argtypes,function.restype=types,None;function(*values)
    app.press('green')
    pump(lambda: app.model.state == State.IN_CALL)
    pump(lambda: api('/api/admin')['callbacks'][0]['status']=='completed')
    assert len(received)==1
    app.press('red');pump(lambda: app.model.state == State.HOME)
    pump(lambda: phone.call is None)

    # A real SIP CANCEL while the terminal rings creates an unread badge.
    phone.dial('sip:term1@127.0.0.1')
    pump(lambda: app.model.state == State.RINGING)
    assert not app.model.missed_calls
    phone.end()
    pump(lambda: app.model.state == State.HOME and phone.call is None)
    app.root.update_idletasks()
    assert app.model.missed_calls == {'phone1'}
    assert app.avatar.find_withtag('missed-call-phone1')
    assert app.missed_calls_store.load(app.model.config) == {'phone1'}
    phone.dial('sip:term1@127.0.0.1')
    pump(lambda: app.model.state == State.RINGING)
    phone.end()
    pump(lambda: app.model.state == State.HOME and phone.call is None)
    assert app.model.notification_count('phone1') == 2
    assert app.corner_notification_state == 2
    assert app.missed_calls_store.load_counts(app.model.config) == {'phone1': 2}

    # Restarting keeps the badge; merely opening confirmation acknowledges it.
    app.close()
    app = Terminal(bootstrap=directory/'terminal.json', profile=test_profile)
    pump(lambda: app.engine and app.engine.registered and app.model.contacts)
    app.engine.core_set_use_files = app.engine.dll.linphone_core_set_use_files
    app.engine.core_set_use_files.argtypes, app.engine.core_set_use_files.restype = [P,I], None
    app.engine.core_set_use_files(app.engine.core, 1)
    assert app.model.missed_calls == {'phone1'}
    assert app.model.notification_count('phone1') == 2 and app.corner_notification_state == 2
    assert app.avatar.find_withtag('missed-call-phone1')
    app.press('green')
    assert app.model.state in (State.CONFIRMING, State.CONFIRM_CALLBACK)
    assert not app.model.missed_calls and app.engine.call is None
    app.press('red')
    assert app.model.state == State.HOME and not app.avatar.find_withtag('missed-call')
    assert not app.missed_calls_store.load(app.model.config)

    # A deliberately declined call and an answered call produce no badge.
    phone.dial('sip:term1@127.0.0.1')
    pump(lambda: app.model.state == State.RINGING)
    app.press('red')
    pump(lambda: app.model.state == State.HOME and phone.call is None)
    assert not app.model.missed_calls
    phone.dial('sip:term1@127.0.0.1')
    pump(lambda: app.model.state == State.RINGING)
    app.press('green')
    pump(lambda: app.model.state == State.IN_CALL)
    # Ordinary phone text creates a badge without disturbing an ongoing call.
    functions = {}
    for name, result, arguments in [
        ('core_get_chat_room_from_uri', P, [P,S]),
        ('chat_room_create_message_from_utf8', P, [P,S]),
        ('chat_message_send', None, [P]),
        ('chat_message_get_state', I, [P]),
        ('chat_message_unref', None, [P])]:
        function = getattr(phone.dll, 'linphone_'+name)
        function.restype, function.argtypes = result, arguments
        functions[name] = function
    room = functions['core_get_chat_room_from_uri'](phone.core, b'sip:term1@127.0.0.1')
    for count, body in enumerate(['Bonjour Evelyn!','Rappelez-moi, merci!'],1):
        message = functions['chat_room_create_message_from_utf8'](room, body.encode())
        assert message
        try:
            functions['chat_message_send'](message)
            pump(lambda: app.model.notification_count('phone1') == count)
            pump(lambda: functions['chat_message_get_state'](message) in (2,6,7))
            assert app.model.state == State.IN_CALL, 'Text interrupted a call'
            assert app.missed_calls_store.load_counts(app.model.config) == {'phone1':count}
        finally:
            functions['chat_message_unref'](message)
    phone.end()
    pump(lambda: app.model.state == State.HOME and phone.call is None)
    assert app.avatar.find_withtag('missed-call-phone1')
    assert app.corner_notification_state == 2
    app.press('green');app.press('red')
    assert not app.model.missed_calls and app.model.state == State.HOME

    # Stop processing the phone's transport without sending an unregister.
    # This emulates a registered phone abruptly losing network connectivity.
    pump(lambda: app.contact_online(app.model.selected))
    disconnected_at = time.monotonic()
    iterate_phone = False
    pump(lambda: not app.contact_online(app.model.selected), 15)
    offline_after = time.monotonic()-disconnected_at
    assert offline_after < 15 and phone.registered
    assert app.avatar.find_withtag('contact-offline')
    app.press('green')
    assert app.model.state == State.CONFIRM_CALLBACK and app.engine.call is None
    app.press('red')
    iterate_phone = True
    pump(lambda: app.contact_online(app.model.selected), 15)
    print(f'Registered phone detected offline in {offline_after:.2f}s; reachability recovered. Phone text badge during call and acknowledgment passed. Callback, missed call, persistence, decline and answer passed.')
finally:
    if phone:
        phone.close()
    if app:
        app.close()
    server.stdin.close()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.terminate();server.wait(timeout=5)
    log.close()
    # Keep the isolated logs to diagnose native failures; no real accounts used.
