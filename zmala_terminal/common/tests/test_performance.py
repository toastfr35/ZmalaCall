"""Regression checks for live configuration, bounded caches and incremental ringing."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.configuration import Configuration
from zmala_terminal.common.model import State
from zmala_terminal.common.render_cache import RenderCache, portrait_size
from zmala_terminal.common.tests.test_terminal import config
from zmala_terminal.common.ui.carousel import CarouselView
from zmala_terminal.common.management import ManagementLoop


class PerformanceTests(unittest.TestCase):
    def test_live_polls_update_presence_without_rewriting_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cache.json'
            client = Configuration({'device_id': 'test'}, path)
            full = config()
            delta = {'configuration_version': 1, 'live': {
                'contacts': [{'id': 'alice', 'online': False}], 'callbacks': []}}
            client.request = Mock(side_effect=[json.dumps(full), json.dumps(delta), json.dumps(full)])
            with patch('zmala_terminal.common.configuration.write_json', wraps=__import__('zmala_terminal.common.json_storage', fromlist=['write_json']).write_json) as writer:
                first = client.fetch()
                first['contacts'][0]['name'] = 'Changed by UI'
                second = client.fetch()
                self.assertEqual(second['contacts'][0]['name'], 'Alice')
                self.assertFalse(second['contacts'][0]['online'])
                third = client.fetch()  # Older servers may always send full configuration.
                self.assertTrue(third['contacts'][0]['online'])
                self.assertEqual(writer.call_count, 1)
            self.assertEqual(client.request.call_args_list[1].args[0], '/api/config?delta=1&version=1')
            stored = json.loads(path.read_text())
            self.assertNotIn('online', stored['contacts'][0])
            self.assertNotIn('callbacks', stored)

    def test_live_update_cannot_change_credentials_or_configuration_version(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Configuration({'device_id': 'test'}, Path(directory) / 'cache.json')
            client.current = config()
            previous = copy.deepcopy(client.current)
            for reply in [
                {'configuration_version': 2, 'live': {'contacts': [], 'callbacks': []}},
                {'configuration_version': 1, 'live': {
                    'contacts': [{'id': 'alice', 'online': 'yes'}], 'callbacks': []}},
            ]:
                client.request = Mock(return_value=json.dumps(reply))
                with self.assertRaises(ValueError):
                    client.fetch()
                self.assertEqual(client.current, previous)

    def test_changed_configuration_is_saved_once_and_live_callbacks_remain_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Configuration({'device_id': 'test'}, Path(directory) / 'cache.json')
            full = config()
            newer = config() | {'configuration_version': 2, 'display_name': 'New name'}
            callback = {'id': 'a'*36, 'from': 'terminal', 'to': 'alice', 'ready': False, 'status': 'pending'}
            delta = {'configuration_version': 2, 'live': {
                'contacts': [{'id': 'alice', 'online': True}], 'callbacks': [callback]}}
            client.request = Mock(side_effect=[json.dumps(full), json.dumps(newer), json.dumps(delta)])
            with patch('zmala_terminal.common.configuration.write_json', wraps=__import__('zmala_terminal.common.json_storage', fromlist=['write_json']).write_json) as writer:
                client.fetch()
                client.fetch()
                received = client.fetch()
                self.assertEqual(writer.call_count, 2)
            self.assertEqual(received['callbacks'], [callback])
            self.assertEqual(client.cached()['display_name'], 'New name')
            client.request = Mock(return_value=json.dumps(full))
            with self.assertRaises(ValueError):
                client.fetch()

    def test_render_cache_preserves_recent_hits_during_eviction(self):
        cache = RenderCache(2)
        cache['active'] = object()
        cache['old'] = object()
        active = cache['active']
        cache['new'] = object()
        self.assertNotIn('old', cache)
        self.assertIs(cache['active'], active)
        for size in range(40, 300):
            self.assertLessEqual(portrait_size(size), size)
            self.assertLess(size-portrait_size(size), 4)
        self.assertEqual(portrait_size(201), portrait_size(200))

    def test_ringing_reuses_portrait_until_geometry_or_contact_changes(self):
        view = CarouselView()
        view.avatar = Mock()
        view.avatar.find_all.return_value = (1, 2, 3)
        view.avatar.winfo_width.return_value = 1000
        view.avatar.winfo_height.return_value = 500
        view.model = Mock(state=State.RINGING, contacts=[], index=0)
        view.language = 'en'
        view.ringing_started = None
        view.draw_card = Mock()
        view.draw_corner_notification = Mock()
        person = {'id': 'alice', 'name': 'Alice'}
        with patch('zmala_terminal.common.ui.carousel.time.monotonic', return_value=100):
            view.draw_avatar(person)
            view.draw_avatar(person)
            view.animate_ringing(100.1)
            self.assertEqual(view.avatar.delete.call_count, 1)
            self.assertEqual(view.draw_card.call_count, 1)
            self.assertGreater(view.avatar.coords.call_count, 2)
            view.avatar.winfo_height.return_value = 600
            view.draw_avatar(person)
            self.assertEqual(view.draw_card.call_count, 2)

    def test_unchanged_presence_does_not_rebuild_home(self):
        loop = ManagementLoop()
        loop.model = Mock(config=config(), state=State.HOME)
        loop.render = Mock()
        loop.apply_poll_config(config())
        loop.render.assert_not_called()
        changed = config()
        changed['contacts'][0]['online'] = False
        loop.apply_poll_config(changed)
        loop.render.assert_called_once()
