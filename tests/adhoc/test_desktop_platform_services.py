"""Windows host compatibility: Pi-only services must not perform hardware work."""
import builtins
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from zmala_terminal.common.platform_services import create_platform_services
from zmala_terminal.common import platform_services


class DesktopPlatformTests(unittest.TestCase):
    def test_factory_does_not_import_linux_modules(self):
        original = builtins.__import__

        def guarded(name, *args, **kwargs):
            if name.startswith('zmala_terminal.linux'):
                raise AssertionError('Desktop factory imported Linux hardware: ' + name)
            return original(name, *args, **kwargs)

        with patch('sys.platform', 'win32'), patch('builtins.__import__', side_effect=guarded):
            services = create_platform_services(Path('fixture'))
            remote = platform_services.create_remote(Mock(), Mock(), Mock())
            sound = platform_services.create_action_sounds()
            pairing = platform_services.create_pairing_status()
            camera = platform_services.create_camera_status()
            self.assertFalse(remote.supported)
            self.assertIsNone(remote.battery)
            self.assertIsNone(pairing.read())
            self.assertIsNone(camera.read())
            sound.play(50, 'green')
            sound.cancel()
            sound.close()
            remote.close()
            with self.assertRaisesRegex(RuntimeError, 'not supported'):
                platform_services.create_tv_check_transport(services.television)
        self.assertFalse(services.usb_power.enabled)
        self.assertTrue(services.usb_power.ready)
        self.assertIsNone(services.usb_power.power_state)
        self.assertFalse(services.television.supports_setup)
        self.assertTrue(services.television.ready(0))
        visible = Mock()
        self.assertFalse(services.television.handle_button(visible))
        visible.assert_not_called()
        self.assertIsNone(services.television.browsing_session())
        services.television.wake()
        services.television.cancel(defer=True)
        services.fan.update(True)
        for service in (services.fan, services.usb_power, services.television):
            service.close()
            service.close()

    def test_disabled_power_retains_ringtone_state_without_playback(self):
        with patch('sys.platform', 'win32'):
            power = create_platform_services(Path('fixture')).usb_power
        power.set_ringtone('example.wav', 75)
        self.assertEqual(power.ringtone_file, Path('example.wav'))
        self.assertEqual(power.ringtone_volume, 75)
        power.preview_tone('example.wav')
        self.assertEqual(power.ringtone_preview_status, 'waiting')
        self.assertFalse(power.playback_active)
        power.stop_preview()
        self.assertEqual(power.ringtone_preview_status, '')
        power.update(True, None, ringing=True)
        self.assertTrue(power.ringing)
        power.stop_ringing()
        self.assertFalse(power.ringing)
        self.assertTrue(power.require(urgent=True))
        power.close()
        power.preview_tone('example.wav')
        self.assertEqual(power.ringtone_preview_status, '')
