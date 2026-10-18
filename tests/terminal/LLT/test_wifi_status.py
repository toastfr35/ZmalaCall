# @test T-LLT-042
# @requirements LLR-TERM-NET-005
# @environment portable
# @plan Supply wireless status independent of Ethernet and unreadable files; assert connected/disconnected/unknown Wi-Fi states cannot be replaced by wired connectivity.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""A wired link must never turn the Wi-Fi status icon green."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.linux import connectivity as linux_connectivity


class WifiStatusTests(unittest.TestCase):
    def test_wireless_status_ignores_ethernet_and_detects_disconnect(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, state in [('eth0', 'up'), ('wlan0', 'down')]:
                (root / name).mkdir()
                (root / name / 'operstate').write_text(state)
            (root / 'wlan0/wireless').mkdir()
            with patch.object(linux_connectivity, 'Path', return_value=root):
                self.assertTrue(linux_connectivity.network_link_available())
                self.assertFalse(linux_connectivity.wifi_link_available())
                (root / 'wlan0/operstate').write_text('up')
                self.assertTrue(linux_connectivity.wifi_link_available())
                (root / 'wlan0/operstate').write_text('down')
                self.assertFalse(linux_connectivity.wifi_link_available())

    def test_unreadable_status_is_unknown(self):
        with patch.object(linux_connectivity, 'Path', side_effect=OSError):
            self.assertIsNone(linux_connectivity.wifi_link_available())


if __name__ == '__main__':
    unittest.main()
