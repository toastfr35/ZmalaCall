"""Late network responses must not affect a reset/re-enrolled terminal."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
import queue

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from management import ManagementLoop
from configuration import validate, Configuration
from test_terminal import config
import json
import tempfile


class ManagementTests(unittest.TestCase):
    def test_wifi_refreshes_during_setup_without_a_server(self):
        loop = ManagementLoop()
        loop.network_worker_busy = loop.worker_busy = False
        loop.generation = 1
        loop.configuration = None
        loop.setup_stage = 'server'
        loop.engine = None
        loop.messages = queue.Queue()
        loop.draw_connectivity = Mock()
        def run_inline(**kwargs):
            return Mock(start=kwargs['target'])
        with patch('management.threading.Thread', side_effect=run_inline), patch('management.wifi_link_available') as wifi:
            for connected in (True, False, None):
                wifi.return_value = connected
                loop.poll()
                loop.drain_messages()
                self.assertIs(loop.network_connected, connected)
                self.assertFalse(loop.network_worker_busy)
            self.assertEqual(wifi.call_count, 3)

    def test_old_worker_results_do_not_change_new_enrollment(self):
        loop = ManagementLoop()
        loop.generation = 2
        loop.worker_busy = True
        loop.network_connected = False
        loop.setup_stage = None
        loop.engine = Mock(registered=True)
        loop.draw_connectivity = Mock()
        loop.apply_poll_config = Mock()
        loop.handle_worker_message('poll-network', (1, True))
        loop.handle_worker_message('poll-config', (1, config()))
        loop.handle_worker_message('poll-done', 1)
        self.assertFalse(loop.network_connected)
        self.assertTrue(loop.worker_busy)
        loop.draw_connectivity.assert_not_called()
        loop.apply_poll_config.assert_not_called()
        loop.handle_worker_message('poll-network', (2, True))
        loop.handle_worker_message('poll-done', 2)
        self.assertTrue(loop.network_connected)
        self.assertFalse(loop.worker_busy)

    def test_malformed_nested_configuration_and_cache_are_rejected(self):
        for value in [None, [], config() | {'sip': []}, config() | {'contacts': [None]}]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate(value, 'test')
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'cache.json'
            cache.write_text(json.dumps([]), encoding='utf-8')
            self.assertIsNone(Configuration({'device_id': 'test'}, cache).cached())
