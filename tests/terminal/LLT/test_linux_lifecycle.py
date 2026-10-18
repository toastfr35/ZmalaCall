# @test T-LLT-069
# @requirements LLR-TERM-START-003, LLR-TERM-START-004, LLR-TERM-START-005, LLR-TERM-UI-018, LLR-TERM-UI-019
# @environment portable
# @plan Invoke kiosk session and launcher helpers with temporary files and mocked subprocess, signal and proc boundaries. Check bounded X11 readiness, supported outputs, owned-child cleanup, profile locking and PID reuse. Read a process start timestamp from a proc fixture whose command contains spaces and parentheses. Inspect Plymouth artwork and Pi 4 presentation configuration; verify private Xauthority ownership without executing real host commands.
# @pass File contents, command arguments, lock behavior and shutdown assertions pass. Launcher tests require Linux and are reported as skips elsewhere.
import contextlib
import io
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from tests.terminal.LLT.test_pi_install import module


class LinuxLifecycleTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'linux', 'Linux supervisor imports fcntl')
    def test_start_timestamp_handles_parentheses_in_process_name(self):
        launcher = module('launcher')
        # Linux proc stat: PID, comm, state, fields 4..21, starttime (field 22).
        stat = '42 (worker (camera) thread) S ' + ' '.join(str(i) for i in range(4, 22)) + ' 987654 23 24\n'
        with patch.object(launcher, 'Path') as path:
            path.return_value.read_text.return_value = stat
            self.assertEqual(launcher.start_time(42), '987654')
            path.assert_called_once_with('/proc/42/stat')
            path.return_value.read_text.side_effect = FileNotFoundError()
            with self.assertRaises(FileNotFoundError):
                launcher.start_time(42)

    def test_plymouth_artwork_and_pi4_present_policy_reference_runtime_assets(self):
        import configparser
        from tests.support.linux_units import ROOT
        theme = configparser.ConfigParser()
        theme.read(ROOT/'build_tools/linux/zmala.plymouth')
        self.assertEqual(theme['Plymouth Theme']['ModuleName'], 'script')
        self.assertEqual(theme['script']['ImageDir'], '/usr/share/plymouth/themes/zmala')
        self.assertTrue(theme['script']['ScriptFile'].endswith('/zmala.script'))
        script = (ROOT/'build_tools/linux/zmala.script').read_text()
        self.assertIn('Image("boot-family.png")', script)
        self.assertIn('Math.Min(Window.GetWidth()', script)
        driver = (ROOT/'build_tools/linux/21-zmalacall-pi4.conf').read_text()
        self.assertIn('Driver "modesetting"', driver)
        self.assertIn('Option "AccelMethod" "msdri3"', driver)

    def test_display_cookie_is_private_owned_and_created_before_xauth(self):
        pwd = Mock()
        pwd.getpwnam.return_value = Mock(pw_uid=1000, pw_gid=1001)
        with patch.dict(sys.modules, {'pwd':pwd}):
            prepare = module('prepare-display')
        with tempfile.TemporaryDirectory() as directory, patch.object(prepare, 'Path', return_value=Path(directory)/'Xauthority'), \
                patch.dict('os.environ', {'ZMALA_USER':'zmala'}), patch.object(prepare.secrets, 'token_hex', return_value='unit-cookie'), \
                patch.object(prepare.subprocess, 'run') as run, patch.object(prepare.os, 'chown', create=True) as chown:
            def authorize(args, **kwargs):
                self.assertTrue((Path(directory)/'Xauthority').is_file())
                self.assertEqual(args, ['xauth', '-f', str(Path(directory)/'Xauthority'), 'add', ':0', '.', 'unit-cookie'])
                self.assertTrue(kwargs['check'])
            run.side_effect = authorize
            prepare.main()
            pwd.getpwnam.assert_called_once_with('zmala')
            chown.assert_called_once_with(Path(directory)/'Xauthority', 1000, 1001)


    def test_x11_wait_retries_timeout_and_has_a_deadline(self):
        kiosk=module('kiosk-session'); now=[0]
        def sleep(seconds): now[0]+=seconds
        with patch.object(kiosk.time,'monotonic',side_effect=lambda:now[0]),patch.object(kiosk.time,'sleep',side_effect=sleep),patch.object(kiosk.subprocess,'run') as run:
            run.side_effect=[subprocess.TimeoutExpired('xdpyinfo',5),Mock(returncode=1),Mock(returncode=0)]
            kiosk.wait_for_display(); self.assertEqual(now[0],1); self.assertEqual(run.call_count,3)
            run.side_effect=None; run.return_value=Mock(returncode=1)
            with self.assertRaisesRegex(RuntimeError,'did not become ready'): kiosk.wait_for_display()
            self.assertEqual(now[0],61)

    def test_display_and_kiosk_shutdown_own_only_their_children(self):
        kiosk=module('kiosk-session')
        with patch.dict(kiosk.os.environ,{'ZMALA_DISPLAY_MODE':'auto'}),patch.object(kiosk.subprocess,'run') as run:
            kiosk.configure_display(); run.assert_not_called()
        query='HDMI-1 connected\n   1280x720 60.0\nHDMI-2 disconnected\n   1280x720 60.0\n'
        with patch.dict(kiosk.os.environ,{'ZMALA_DISPLAY_MODE':'1280x720'}),patch.object(kiosk.subprocess,'run',return_value=Mock(stdout=query)) as run:
            kiosk.configure_display(); self.assertEqual(run.call_count,2); self.assertEqual(run.call_args.args[0],['xrandr','--output','HDMI-1','--mode','1280x720','--rate','60'])
        for failed in [False,True]:
            manager=Mock(); child=Mock(); child.poll.return_value=None; child.wait.return_value=7
            if failed: manager.wait.side_effect=[subprocess.TimeoutExpired('openbox',5),0]
            handlers={}
            def wait(): handlers[signal.SIGTERM](signal.SIGTERM,None); return 7
            child.wait.side_effect=wait
            with patch.object(kiosk,'wait_for_display'),patch.object(kiosk,'configure_display'),patch.object(kiosk.subprocess,'run') as run,patch.object(kiosk.subprocess,'Popen',side_effect=[manager,child]) as popen,patch.object(kiosk.signal,'signal',side_effect=lambda sig,fn:handlers.update({sig:fn})):
                self.assertEqual(kiosk.main(),7)
            self.assertEqual([c.args[0] for c in run.call_args_list],[['xset','s','off'],['xset','-dpms']])
            self.assertIn('--fullscreen',popen.call_args.args[0]); child.terminate.assert_called_once(); manager.terminate.assert_called_once()
            self.assertEqual(manager.kill.call_count,int(failed))

    @unittest.skipUnless(sys.platform=='linux','Linux supervisor uses fcntl process locks')
    def test_launcher_run_lock_and_shutdown_record_lifetime(self):
        launcher=module('launcher')
        with tempfile.TemporaryDirectory() as directory,contextlib.ExitStack() as stack:
            folder=Path(directory); stack.enter_context(patch.object(launcher,'ROOT',folder)); stack.enter_context(patch.dict(launcher.os.environ,{'ZMALA_RUNTIME_DIR':directory}))
            stack.enter_context(patch.object(launcher.os,'umask')); stack.enter_context(patch.object(launcher.os,'getpid',return_value=4321)); stack.enter_context(patch.object(launcher,'start_time',return_value='boot-tick'))
            stack.enter_context(patch.object(sys,'argv',['launcher','run','--profile','test','--fullscreen'])); stack.enter_context(patch.object(sys,'path',list(sys.path)))
            flock=stack.enter_context(patch.object(launcher.fcntl,'flock')); handlers={}
            stack.enter_context(patch.object(launcher.signal,'signal',side_effect=lambda sig,fn:handlers.update({sig:fn})))
            record=folder/'test.pid.json'
            def app(*args,**kwargs):
                self.assertEqual(json.loads(record.read_text()),{'pid':4321,'started':'boot-tick'})
                self.assertEqual(sys.argv[1:],['--profile','test','--fullscreen']); handlers[signal.SIGTERM](signal.SIGTERM,None)
            run=stack.enter_context(patch.object(launcher.runpy,'run_path',side_effect=app)); launcher.main()
            self.assertFalse(record.exists()); run.assert_called_once()
            sys.argv=['launcher','run','--profile','test']; flock.side_effect=BlockingIOError()
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as error: launcher.main()
            self.assertEqual(error.exception.code,2); self.assertFalse(record.exists())

    @unittest.skipUnless(sys.platform=='linux','Linux supervisor uses fcntl process locks')
    def test_launcher_start_validates_profile_display_and_reports_child_failure(self):
        launcher=module('launcher')
        with tempfile.TemporaryDirectory() as directory,contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(launcher,'ROOT',Path(directory))); stack.enter_context(patch.dict(launcher.os.environ,{'ZMALA_RUNTIME_DIR':directory,'DISPLAY':':test'})); stack.enter_context(patch.object(launcher.os,'umask')); stack.enter_context(patch.object(launcher.time,'sleep'))
            process=Mock(pid=4321); process.poll.return_value=None; popen=stack.enter_context(patch.object(launcher.subprocess,'Popen',return_value=process))
            stack.enter_context(patch.object(sys,'argv',['launcher','start','--profile','test','--fullscreen']))
            with contextlib.redirect_stdout(io.StringIO()): launcher.main()
            self.assertTrue(popen.call_args.kwargs['start_new_session']); self.assertIn('--fullscreen',popen.call_args.args[0])
            process.poll.return_value=1
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit): launcher.main()
            with patch.dict(launcher.os.environ,{'DISPLAY':''}),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit): launcher.main()
            sys.argv=['launcher','start','--profile','../escape']
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit): launcher.main()

    @unittest.skipUnless(sys.platform=='linux','Linux supervisor uses fcntl process locks')
    def test_stop_rejects_pid_reuse_and_escalates_only_matching_supervisor(self):
        launcher=module('launcher')
        with tempfile.TemporaryDirectory() as directory,contextlib.ExitStack() as stack:
            folder=Path(directory); record=folder/'test.pid.json'
            stack.enter_context(patch.object(launcher,'ROOT',folder)); stack.enter_context(patch.dict(launcher.os.environ,{'ZMALA_RUNTIME_DIR':directory})); stack.enter_context(patch.object(launcher.os,'umask'))
            stack.enter_context(patch.object(sys,'argv',['launcher','stop','--profile','test'])); stack.enter_context(patch.object(launcher.time,'sleep')); kill=stack.enter_context(patch.object(launcher.os,'killpg'))
            start=stack.enter_context(patch.object(launcher,'start_time',return_value='new-tick')); record.write_text(json.dumps({'pid':4321,'started':'old-tick'}))
            with contextlib.redirect_stdout(io.StringIO()): launcher.main()
            kill.assert_not_called(); self.assertFalse(record.exists())
            start.return_value='old-tick'; proc=Mock(); proc.read_bytes.return_value=b'other\0run\0'
            real_path=Path
            def paths(value): return proc if str(value).startswith('/proc/') else real_path(value)
            stack.enter_context(patch.object(launcher,'Path',side_effect=paths)); record.write_text(json.dumps({'pid':4321,'started':'old-tick'}))
            with self.assertRaisesRegex(RuntimeError,'different process'): launcher.main()
            kill.assert_not_called(); self.assertTrue(record.exists())
            proc.read_bytes.return_value=str(Path(launcher.__file__).resolve()).encode()+b'\0run\0'; proc.exists.return_value=True; proc.read_text.return_value='4321 (zmala) S rest'
            with contextlib.redirect_stdout(io.StringIO()): launcher.main()
            self.assertEqual([c.args for c in kill.call_args_list],[(4321,signal.SIGTERM),(4321,signal.SIGKILL)]); self.assertFalse(record.exists())


if __name__=='__main__': unittest.main()
