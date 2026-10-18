# @test T-LLT-065
# @requirements LLR-TERM-TV-019, LLR-TERM-TV-020, LLR-TERM-TV-022, LLR-TERM-TV-023, LLR-TERM-TV-024
# @environment portable
# @plan Drive the Linux setup transport with temporary EDID/config files, a virtual cancellation clock and mocked CEC, UDP discovery and HTTP/WebSocket boundaries. Verify device identity binding, route-change rejection, standby/wake recovery, source cancellation, bounded discovery without advertised URLs/redirects, and paired-credential cleanup/persistence only after consent remains active.
# @pass No commands reach a real TV. Assertions establish transport sequencing, isolation and cleanup; physical switching still requires the user-confirmed installation checks.
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from zmala_terminal.linux import tv_check


class Clock:
    def __init__(self): self.now=0; self.cancelled=False; self.waits=[]
    def is_set(self): return self.cancelled
    def wait(self,seconds): self.waits.append(seconds); self.now+=seconds; return self.cancelled


class TVTransportTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.folder=Path(temp.name)
        self.tv=Mock(); self.tv._lock=threading.Lock(); self.tv._samsung.config_file=self.folder/'tv.json'
        self.tv.device=str(self.folder/'cec0'); Path(self.tv.device).touch(); self.tv.command='cec-ctl'
        self.tv._physical_address.return_value='2.0.0.0'; self.clock=Clock()
        timer=patch.object(tv_check.time,'monotonic',side_effect=lambda:self.clock.now); timer.start(); self.addCleanup(timer.stop)
        self.transport=tv_check.CheckTransport(self.tv); self.transport.address='2.0.0.0'
        self.tv._run.side_effect=lambda *args: '2.0.0.0' if args==('--physical-address',) else '4' if args==('--logical-address',) else 'pwr-state: standby (1)'

    def test_probe_clears_leases_and_binds_only_matching_connector_edid(self):
        output=self.folder/'card1-HDMI-A-1'; output.mkdir(); (output/'connector_id').write_text('7'); (output/'edid').write_bytes(b'television-edid')
        with patch.object(tv_check,'connector',return_value=(1,7)), patch.object(Path,'glob',return_value=[output]):
            result=self.transport.probe(self.clock)
        self.assertEqual(result,{'address':'2.0.0.0','display':hashlib.sha256(b'television-edid').hexdigest()})
        self.assertIsNone(self.tv._previous); self.assertIsNone(self.tv._restore_pending); self.assertFalse(self.tv._changed)
        self.tv._ready.set.assert_called_once(); self.tv.pause_for_setup.assert_called_once()
        with patch.object(tv_check,'connector',return_value=None): self.assertIsNone(self.transport.probe(self.clock)['display'])
        self.tv._physical_address.return_value=None; self.assertIsNone(self.transport.probe(self.clock))
        self.tv.command=None; self.assertIsNone(self.transport.probe(self.clock))

    def test_resume_requires_readable_network_binding_and_prepare_checks_route(self):
        self.transport.resume_network(True); self.assertFalse(self.tv._samsung.enabled)
        self.tv._samsung.config_file.write_text(json.dumps({'terminal_source':{'address':'2.0.0.0'}}))
        self.transport.resume_network(True); self.assertTrue(self.tv._samsung.enabled); self.assertIsNone(self.transport.trial_key)
        self.tv._samsung.config_file.write_text('{}'); self.transport.resume_network(True); self.assertEqual(self.transport.trial_key,'KEY_HDMI')
        self.transport.resume_network(False); self.assertFalse(self.tv._samsung.enabled)
        self.tv._run.side_effect=['3.0.0.0']
        with self.assertRaisesRegex(RuntimeError,'route changed'): self.transport.prepare(self.clock)
        self.tv._run.side_effect=['2.0.0.0','1','']; self.transport.prepare(self.clock)
        self.tv._run.assert_called_with('--playback','--cec-version-1.4','--osd-name','ZmalaCall')

    def test_power_retries_wake_and_reports_incomplete_acknowledgements(self):
        self.assertTrue(self.transport.power(self.clock)); self.assertEqual(self.clock.waits,[3,0,2,3,3])
        self.assertEqual(sum('--image-view-on' in c.args for c in self.tv._run.call_args_list),4)
        def no_wake(*args):
            if '--image-view-on' in args: raise OSError('temporary wake failure')
            if args==('--physical-address',): return '2.0.0.0'
            if args==('--logical-address',): return '4'
            return 'pwr-state: on (0)'
        self.tv._run.side_effect=no_wake
        with self.assertRaisesRegex(RuntimeError,'acknowledgement'): self.transport.power(self.clock)
        self.assertGreaterEqual(self.clock.now,20)

    def test_source_broadcast_roundtrip_and_cancel_never_reselect_after_cancellation(self):
        self.tv._previous_source.return_value='0.0.0.0'; self.assertTrue(self.transport.source(self.clock))
        self.tv._samsung.restore_broadcast.assert_called_once(); self.assertEqual(self.clock.waits,[3,3])
        self.clock.wait=lambda _:setattr(self.clock,'cancelled',True) or True
        self.tv._run.reset_mock(); self.assertFalse(self.transport.source(self.clock))
        self.assertEqual(sum('--active-source' in c.args for c in self.tv._run.call_args_list),1)
        self.clock.cancelled=False; self.transport.trial_key='KEY_HDMI'; self.tv._run.side_effect=OSError('CEC unavailable')
        self.tv._samsung._send_key.return_value=True; self.transport.select_terminal(self.clock)
        self.tv._samsung._send_key.assert_called_once()
        self.tv._samsung._send_key.return_value=False
        with self.assertRaisesRegex(OSError,'CEC unavailable'): self.transport.select_terminal(self.clock)

    def test_discovery_ignores_advertised_urls_redirects_and_bad_payloads(self):
        udp=Mock(); packets=iter([(b'samsung LOCATION: http://untrusted/path',('192.0.2.2',1900)),
                                 (b'other',('192.0.2.99',1900)),(b'SAMSUNG',('192.0.2.3',1900)),
                                 (b'samsung',('192.0.2.4',1900)),(b'samsung',('192.0.2.5',1900))])
        def receive(_):
            self.clock.now+=.5
            try: return next(packets)
            except StopIteration: raise socket.timeout()
        udp.recvfrom.side_effect=receive; responses=[]
        for host,payload,redirect in [('192.0.2.2',{'device':{'modelName':'TV','name':'Living room'}},False),
                                      ('192.0.2.3',{},True),('192.0.2.4',{'device':{'modelName':3}},False),
                                      ('192.0.2.5',[],False)]:
            response=Mock(); response.geturl.return_value='http://attacker/' if redirect else f'http://{host}:8001/api/v2/'
            response.read.return_value=json.dumps(payload).encode(); wrapper=Mock(); wrapper.__enter__=Mock(return_value=response); wrapper.__exit__=Mock(return_value=False); responses.append(wrapper)
        opener=Mock(); opener.open.side_effect=responses
        with patch.object(tv_check.socket,'socket') as create,patch.object(tv_check.urllib.request,'build_opener',return_value=opener):
            create.return_value.__enter__.return_value=udp
            self.assertEqual(self.transport.discover(self.clock),[{'host':'192.0.2.2','name':'Living room'}])
        udp.settimeout.assert_called_once_with(.3); self.assertEqual(udp.recvfrom.call_args.args,(8192,))
        self.assertEqual([call.args[0].full_url for call in opener.open.call_args_list],[f'http://192.0.2.{i}:8001/api/v2/' for i in range(2,6)])
        for call in opener.open.call_args_list: self.assertEqual(call.kwargs,{'timeout':1})
        self.assertIsNone(tv_check.NoRedirect().redirect_request(None,None,302,'',{},'http://bad/'))

    def test_pair_closes_socket_on_success_cancel_and_save_failure_then_binds_verified_key(self):
        for cancelled,failure in ((False,False),(True,False),(False,True)):
            self.clock.cancelled=cancelled; remote=Mock(); saved={'host':'192.0.2.2','token':'secret'}
            with patch.object(tv_check,'connect',return_value=(remote,saved)) as connect,patch.object(tv_check,'save_config') as save:
                if failure: save.side_effect=OSError('disk full')
                if failure:
                    with self.assertRaises(OSError): self.transport.pair(self.clock,'192.0.2.2')
                else: self.assertTrue(self.transport.pair(self.clock,'192.0.2.2'))
                connect.assert_called_once_with('192.0.2.2',timeout=25); remote.close.assert_called_once_with(timeout=0)
                if cancelled: save.assert_not_called()
                else: save.assert_called_once_with(self.tv._samsung.config_file,saved)
        self.tv._samsung.config_file.write_text(json.dumps(saved)); self.transport.trial_key='KEY_HDMI'
        with patch.object(tv_check,'save_config') as save: self.transport.confirm_source()
        self.assertEqual(save.call_args.args[1]['terminal_source'],{'address':'2.0.0.0','key':'KEY_HDMI'})


if __name__=='__main__': unittest.main()
