# @test T-HLT-043
# @requirements HLR-TERM-MAINT-027
# @environment portable
# @plan Drive real local lease/status files through terminal eligibility calculation, including pending configuration/network/console workers; assert USB hold precedes acknowledgement and then deliver incoming call and remote-input callbacks.
# @pass Busy call/setup/settings/held-input states cannot grant maintenance; acknowledged maintenance rejects new calls before USB/TV actions.
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock
from zmala_terminal.common.update_client import UpdateClient,tick_terminal
from zmala_terminal.common.model import State
from zmala_terminal.common.call_control import CallControl

@unittest.skipUnless(os.name=='posix','POSIX IPC')
class AdmissionIntegrationTests(unittest.TestCase):
    def test_inactivity_and_busy_states_fence_before_acknowledgement(self):
        for busy in ('call','setup','settings','write','key','recent','worker','network','console','tv','usb',None):
            with self.subTest(busy=busy),tempfile.TemporaryDirectory() as folder:
                request=Path(folder)/'request';status=Path(folder)/'status'
                request.write_text(json.dumps({'nonce':'a'*32,'heartbeat':200,'phase':'request'}))
                client=UpdateClient(request,status,lambda:200,os.getuid())
                app=SimpleNamespace(update_client=client,model=SimpleNamespace(state=State.HOME),engine=Mock(),
                    setup_stage=None,settings_open=False,setup_busy=False,settings_draft=SimpleNamespace(busy=False),
                    keys_down=set(),last_button=0,language='fr',closed=False,usb_power=SimpleNamespace(enabled=True,powered=False))
                app.engine.call=None
                app.usb_power.hold_for_update=Mock(side_effect=lambda: self.assertFalse(status.exists()))
                app.maintenance=SimpleNamespace(busy=busy=='console',stop=Mock())
                app.worker_busy=busy=='worker';app.network_worker_busy=busy=='network'
                app.tv_control=SimpleNamespace(session=SimpleNamespace(browsing={} if busy!='tv' else {'previous':'live'},previous=None))
                app.usb_power.state='switching' if busy=='usb' else 'off'
                if busy=='call':app.engine.call=object()
                if busy=='setup':app.setup_stage='wifi'
                if busy=='settings':app.settings_open=True
                if busy=='write':app.settings_draft.busy=True
                if busy=='key':app.keys_down={'green'}
                if busy=='recent':app.last_button=199
                tick_terminal(app,200)
                self.assertEqual(json.loads(status.read_text())['maintenance'],busy is None)
                if busy is None:
                    app.usb_power.hold_for_update.assert_called_once()
                    CallControl.call_event(app,'incoming',1,'caller','domain')
                    app.engine.call_decline.assert_called_once_with('incoming',6)
                    request.write_text(json.dumps({'nonce':'a'*32,'heartbeat':200,'phase':'checking'}))
                    client.passive=True;client.next_tick=0;app.usb_power.powered=None
                    tick_terminal(app,200)
                    self.assertTrue(json.loads(status.read_text())['sleeping'])
