# @test T-LLT-095
# @requirements LLR-TERM-MAINT-028
# @environment portable
# @plan Use temporary local IPC and deterministic clocks to grant/defer/expire leases and retain trial fencing; test malformed/symlink requests, passive-state release and call/input/native-media guards.
# @pass Only eligible current requests are acknowledged; maintenance blocks call/input wake paths and passive startup avoids media settings/volume work. POSIX IPC cases skip on Windows.
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
from zmala_terminal.common.update_client import UpdateClient
from zmala_terminal.common.call_control import CallControl
from zmala_terminal.common.input_control import InputControl
from zmala_terminal.common.engine import Engine

class UpdateClientTests(unittest.TestCase):
    def test_tv_shutdown_during_update_does_not_start_restoration(self):
        from zmala_terminal.linux.tv_control import TVControl
        television = TVControl(device='/fixture/not-a-cec-device')
        television.cancel = Mock()
        television.hold_for_update()
        television.close()
        television.cancel.assert_not_called()

    def test_deferred_usb_does_not_start_or_restore_power_until_activity(self):
        from zmala_terminal.linux.usb_power import UsbPower
        with patch('zmala_terminal.linux.usb_power.sys.platform', 'linux'), patch.dict(os.environ, {'ZMALA_USB_POWER': '1'}), patch('zmala_terminal.linux.usb_power.threading.Thread') as thread:
            power = UsbPower(Path('.'), defer=True)
            thread.assert_not_called()
            power.command = Mock()
            power.hold_for_update()
            power.stopped = True
            power.run()
            power.command.assert_not_called()
            power.stopped = False
            power.require()
            thread.assert_called_once()
            self.assertFalse(power.preserve_shutdown)
            power.close()

    def test_admitted_calls_and_buttons_do_not_touch_media_or_model(self):
        app=SimpleNamespace(update_client=SimpleNamespace(locked=True),engine=Mock(),model=Mock(),usb_power=Mock())
        CallControl.call_event(app,'incoming',1,'caller','domain')
        app.engine.call_decline.assert_called_once_with('incoming',6)
        app.model.incoming.assert_not_called();app.usb_power.require.assert_not_called()
        self.assertEqual(InputControl.keypress(app,'green'),'break')
        CallControl.action(app,'dial');app.engine.dial.assert_not_called()
        passive=SimpleNamespace(defer_media=True)
        Engine.apply_settings(passive,{})
        self.assertIsNone(Engine.apply_speaker_volume(passive))

    @unittest.skipUnless(os.name=='posix','POSIX no-follow IPC')
    def test_lease_freshness_and_passive_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);request=root/'request';status=root/'status';now=[100]
            value={'nonce':'a'*32,'heartbeat':100,'phase':'request','preserve_sleep':True}
            request.write_text(json.dumps(value));client=UpdateClient(request,status,lambda:now[0],os.getuid())
            client.tick(False,'fr',True,True);self.assertFalse(client.locked)
            fence=Mock(side_effect=lambda: self.assertFalse(status.exists() and json.loads(status.read_text())['maintenance']))
            now[0]+=1;client.tick(True,'fr',True,True,on_fence=fence)
            fence.assert_called_once()
            reply=json.loads(status.read_text());self.assertTrue(reply['maintenance']);self.assertEqual(reply['language'],'fr')
            self.assertTrue(client.passive)
            now[0]=115;client.tick(False,'fr',True,True);self.assertFalse(client.locked)
            value.update(phase='checking',heartbeat=115);request.write_text(json.dumps(value));client.refresh()
            self.assertTrue(client.locked)
            now[0]=130;client.tick(False,'fr',True,True);self.assertTrue(client.locked)
            value.update(phase='idle',heartbeat=130);request.write_text(json.dumps(value));client.refresh()
            self.assertFalse(client.locked);client.activity();self.assertFalse(client.passive)
            client.refresh();self.assertFalse(client.passive)
            request.unlink();request.symlink_to(status)
            self.assertIsNone(client.refresh())
            request.unlink();request.write_text('{');self.assertIsNone(client.refresh())
