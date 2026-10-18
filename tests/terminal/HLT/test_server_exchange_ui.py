# @test T-HLT-022
# @requirements HLR-TERM-COM-001, HLR-TERM-COM-002, HLR-TERM-CONFIG-017, HLR-TERM-NET-002
# @environment display
# @plan Run real Tk controllers, HTTP Configuration requests and atomic cache writes against an isolated endpoint. Return valid, invalid, unauthorized and delayed responses, change enrollment generations and edit settings. Check UI responsiveness, independent Wi-Fi/server indications, acceptance-only revisions and deferred media changes during a simulated native call.
# @pass Invalid and obsolete replies preserve accepted state; only acknowledged edits are applied; navigation continues during blocked I/O; in-call changes retain the native call. Network and native media devices are substituted, so this is not physical Wi-Fi or call-quality acceptance.

import copy
import json
import os
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

from zmala_terminal.common.configuration import Configuration
from zmala_terminal.common.local_settings import FIELDS
from zmala_terminal.common.model import State
from tests.support.terminal.ui_fixture import terminal_fixture, pump
from tests.support.terminal.config_endpoint import config_endpoint


@unittest.skipUnless(sys.platform == 'linux' and os.environ.get('DISPLAY'), 'Linux Tk display required')
class ServerExchangeTests(unittest.TestCase):
    def test_validated_http_cache_and_independent_status_recover_after_errors(self):
        with terminal_fixture() as (app, directory), config_endpoint() as server, \
                patch('zmala_terminal.common.management.wifi_link_available', return_value=False):
            app.configuration = Configuration(server.bootstrap, directory/'cache.json')
            app.poll()
            pump(app, lambda: not app.worker_busy and not app.network_worker_busy)
            self.assertTrue(server.requests)
            self.assertTrue(all(auth == 'Bearer fixture-bearer-token' for _, auth, _ in server.requests))
            self.assertFalse(app.network_connected)
            self.assertTrue(app.connection_drawn[1], 'Server must stay reachable without Wi-Fi')
            accepted = (directory/'cache.json').read_bytes()
            snapshot = json.loads(accepted)
            self.assertNotIn('callbacks', snapshot)
            self.assertTrue(all('online' not in c for c in snapshot['contacts']))
            for change, code in [({'device_id': 'other'}, 200), ({'contacts': [{}]}, 200), ({}, 401)]:
                original = copy.deepcopy(server.current)
                server.current.update(change); server.code = code
                app.poll(); pump(app, lambda: not app.worker_busy)
                self.assertEqual((directory/'cache.json').read_bytes(), accepted)
                self.assertEqual(app.model.config['device_id'], 'trace-fixture')
                server.current, server.code = original, 200
            app.server_seen = time.monotonic() - 20
            app.network_connected = True
            app.draw_connectivity(True)
            self.assertTrue(app.connection_drawn[0])
            self.assertFalse(app.connection_drawn[1])
            server.current['configuration_version'] = 2
            server.current['contacts'][0]['name'] = 'Updated contact'
            app.poll(); pump(app, lambda: not app.worker_busy)
            self.assertEqual(app.model.config['configuration_version'], 2)
            self.assertEqual(app.model.contacts[0]['name'], 'Updated contact')

    def test_delayed_worker_cannot_replace_newer_configuration_or_enrollment(self):
        with terminal_fixture() as (app, directory), config_endpoint() as server, \
                patch('zmala_terminal.common.management.wifi_link_available', return_value=True):
            app.configuration = Configuration(server.bootstrap, directory/'cache.json')
            server.gate = threading.Event()
            app.poll()
            self.assertTrue(server.entered.wait(2))
            app.press('right')
            self.assertEqual(app.model.index, 1, 'HTTP must not block navigation')
            newer = copy.deepcopy(app.model.config)
            newer['configuration_version'] = 3
            app.apply_poll_config(newer)
            server.gate.set()
            pump(app, lambda: not app.worker_busy)
            self.assertEqual(app.model.config['configuration_version'], 3)
            server.gate = threading.Event(); server.entered.clear()
            app.handle_worker_message = Mock(wraps=app.handle_worker_message)
            old_generation = app.generation
            app.poll(); self.assertTrue(server.entered.wait(2))
            app.generation += 1
            server.gate.set()
            # The old worker is allowed to finish, but its generation cannot alter the UI.
            pump(app, lambda: any(c.args == ('poll-done', old_generation)
                                 for c in app.handle_worker_message.call_args_list))
            self.assertEqual(app.model.config['configuration_version'], 3)
            self.assertTrue(app.worker_busy, 'Old completion must not clear a newer generation flag')

    def test_settings_acceptance_and_in_call_changes_keep_media_owner(self):
        with terminal_fixture() as (app, directory), config_endpoint() as server:
            app.configuration = Configuration(server.bootstrap, directory/'cache.json')
            app.configuration.fetch()
            app.settings_open = True
            app.settings_draft.row = FIELDS.index('carousel_portraits')
            app.press('green'); app.press('right')
            self.assertEqual(app.model.config.get('carousel_portraits', 3), 3)
            server.settings_code = 409
            app.press('green')
            pump(app, lambda: not app.settings_draft.busy)
            self.assertTrue(app.settings_draft.error)
            self.assertEqual(app.model.config.get('carousel_portraits', 3), 3)
            server.settings_code = 200
            app.press('green'); pump(app, lambda: not app.settings_draft.busy)
            self.assertFalse(app.settings_draft.editing)
            self.assertEqual(app.model.config['carousel_portraits'], 5)
            self.assertEqual(json.loads((directory/'cache.json').read_text())['carousel_portraits'], 5)
            app.settings_open = False
            app.model.contact = app.model.contacts[0]
            app.model.state = State.IN_CALL
            engine = app.engine
            engine.call = 123
            changed = copy.deepcopy(app.model.config) | {'configuration_version': 3, 'language': 'fr', 'auto_framing': True, 'video_resolution': '1080p'}
            app.apply_poll_config(changed)
            self.assertIs(app.engine, engine)
            self.assertEqual(app.engine.call, 123)
            engine.close.assert_not_called(); engine.end.assert_not_called()
            engine.auto_framing.configure.assert_called_with(True)
            self.assertEqual(app.language, 'fr')
            self.assertEqual(app.pending_config['video_resolution'], '1080p')
