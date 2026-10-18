"""Controlled HTTP peer for terminal boundary/failure integration scenarios."""
from contextlib import contextmanager
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

from tests.support.terminal.ui_fixture import configuration


@contextmanager
def config_endpoint():
    class State:
        current = configuration()
        requests = []
        code = 200
        gate = None
        entered = threading.Event()
        settings_code = 200

    state = State()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def dispatch(self):
            length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(length)) if length else None
            state.requests.append((self.path, self.headers.get('Authorization'), data))
            response, code = copy.deepcopy(state.current), state.code
            if self.path == '/api/device/settings':
                code = state.settings_code
                if code == 200:
                    state.current.update(data['settings'])
                    state.current['configuration_version'] += 1
                    response = copy.deepcopy(state.current)
            if self.path == '/api/status':
                response, code = {'ok': True}, 200
            gate = state.gate
            state.entered.set()
            if gate is not None:
                gate.wait(3)
            payload = json.dumps(response).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = dispatch

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.bootstrap = {'server_url': f'http://127.0.0.1:{server.server_port}',
                       'device_id': 'trace-fixture', 'device_token': 'fixture-bearer-token'}
    try:
        yield state
    finally:
        if state.gate is not None:
            state.gate.set()
        server.shutdown()
        server.server_close()
        thread.join(3)
