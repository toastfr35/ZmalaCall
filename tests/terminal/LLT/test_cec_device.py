# @test T-LLT-010
# @requirements LLR-TERM-TV-025
# @environment portable
# @plan Supply synthetic DRM connectors and hotplug layouts; assert selection follows the active HDMI connector and preserves explicit adapter/restore choices. Inject the Linux connector-info ioctl response and verify DRM union decoding, unknown types, exact request arguments and file closure on errors.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Dual-HDMI selection follows kernel connector identity, not device numbering."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import mock_open, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.linux.cec_device import connector, select_device
from zmala_terminal.linux.tv_control import TVControl


class CecDeviceTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith('linux'), 'Kernel ioctl adapter requires Linux')
    def test_connector_decodes_drm_identity_and_closes_on_failed_ioctl(self):
        import struct
        opened = mock_open()
        def ioctl(stream, operation, data, mutate):
            self.assertIs(stream, opened.return_value.__enter__.return_value)
            self.assertEqual(operation, 0x8044610a)
            self.assertEqual(len(data), 68)
            self.assertTrue(mutate)
            struct.pack_into('=III', data, 0, 1, 7, 44)
        with patch('builtins.open', opened), patch('fcntl.ioctl', side_effect=ioctl):
            self.assertEqual(connector('/dev/cec1'), (7, 44))
        opened.assert_called_once_with('/dev/cec1', 'rb', buffering=0)
        opened.return_value.__exit__.assert_called_once()
        with patch('builtins.open', mock_open()), patch('fcntl.ioctl'):
            self.assertIsNone(connector('/dev/cec1'))
        opened = mock_open()
        with patch('builtins.open', opened), patch('fcntl.ioctl', side_effect=OSError('unplugged')):
            with self.assertRaisesRegex(OSError, 'unplugged'):
                connector('/dev/cec1')
        opened.return_value.__exit__.assert_called_once()

    def test_second_hdmi_and_hotplug_with_different_card_number(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            devices, drm = root / 'dev', root / 'drm'
            devices.mkdir()
            drm.mkdir()
            for number in (0, 1):
                (devices / f'cec{number}').touch()
            first, second = str(devices / 'cec0'), str(devices / 'cec1')
            outputs = []
            for number, identifier, status in [(1, 35, 'disconnected'), (2, 44, 'connected')]:
                output = drm / f'card7-HDMI-A-{number}'
                output.mkdir()
                (output / 'connector_id').write_text(str(identifier))
                (output / 'status').write_text(status)
                outputs.append(output)
            with patch('zmala_terminal.linux.cec_device.connector', side_effect=lambda d: (7, 35 if d == first else 44)):
                self.assertEqual(select_device(first, devices, drm), second)
                (outputs[0] / 'status').write_text('connected')
                self.assertEqual(select_device(second, devices, drm), second)
                # Boot-forced unused HDMI must not trap a running observer.
                (outputs[0] / 'edid').write_bytes(bytes(128))
                (outputs[0] / 'enabled').write_text('enabled')
                (outputs[1] / 'edid').write_bytes(b'')
                (outputs[1] / 'enabled').write_text('disabled')
                self.assertEqual(select_device(second, devices, drm), first)
                # With two real TVs, prefer the one receiving scanout.
                (outputs[1] / 'edid').write_bytes(bytes(128))
                self.assertEqual(select_device(second, devices, drm), first)
                (outputs[1] / 'enabled').write_text('enabled')
                self.assertEqual(select_device(second, devices, drm), second)
                (outputs[1] / 'status').write_text('disconnected')
                self.assertEqual(select_device(second, devices, drm), first)
                (outputs[0] / 'status').write_text('disconnected')
                self.assertEqual(select_device(second, devices, drm), second)
            with patch('zmala_terminal.linux.cec_device.connector', side_effect=OSError('unsupported ioctl')):
                self.assertEqual(select_device(None, devices, drm), first)

    def test_explicit_adapter_and_saved_restore_are_not_redirected(self):
        fixed = TVControl(device='/dev/cec0')
        fixed.command = 'cec-ctl'
        with patch('zmala_terminal.linux.tv_control.select_device', return_value='/dev/cec1') as select:
            fixed._refresh_device()
            select.assert_not_called()
            automatic = TVControl()
            automatic.command = 'cec-ctl'
            automatic.device = '/dev/cec0'
            automatic._address = '2.0.0.0'
            automatic.session.previous = {'address': '2.0.0.0'}
            automatic._refresh_device()
            self.assertEqual(automatic.device, '/dev/cec0')
            automatic.session.previous = None
            automatic._refresh_device()
            self.assertEqual(automatic.device, '/dev/cec1')
            self.assertIsNone(automatic._address)


if __name__ == '__main__':
    unittest.main()
