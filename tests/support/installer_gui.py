"""Real Tk controls with substituted SSH, dialogs and worker scheduling."""
import os
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import Mock, patch


class InstallerUIContract:
    def setUp(self):
        try:
            probe = tk.Tk(); probe.withdraw(); probe.destroy()
        except tk.TclError as error:
            self.skipTest('Tk display required (use xvfb-run on Linux): ' + str(error))
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        environment = patch.dict(os.environ, {'LOCALAPPDATA': temporary.name})
        environment.start(); self.addCleanup(environment.stop)
        dialogs = patch.object(self.module, 'messagebox')
        self.dialogs = dialogs.start(); self.addCleanup(dialogs.stop)
        self.app = self.module.Installer(); self.app.withdraw()
        self.addCleanup(self.cleanup_window)
        self.target = Mock(info={'hostname':'test', 'model':'Raspberry Pi 4 Model B',
                                'ssh_address':'192.0.2.1', 'os':{'PRETTY_NAME':'Trixie'}, 'installed':False},
                           key='SHA256:verified', wired_address='192.0.2.1')
        self.target.check.return_value = self.target.info

    def cleanup_window(self):
        app = self.app
        try:
            app.progress.stop()
            for timer in app.tk.splitlist(app.tk.call('after', 'info')):
                app.tk.call('after', 'cancel', timer)
            app.destroy()
        except tk.TclError:
            pass
        finally:
            getattr(app, 'log_file', getattr(app, 'log', None)).close()

    def run_worker(self, *args, **kwargs):
        thread = Mock()
        thread.start.side_effect = kwargs['target']
        return thread

    def test_initial_state_and_address_change_invalidate_preflight(self):
        app = self.app
        self.assertEqual(str(app.install_button.cget('state')), 'disabled')
        self.assertFalse(app.busy)
        app.target = self.target; app.busy = True; app.invalidate()
        self.target.close.assert_not_called()
        app.busy = False; app.host.set('new-target.local')
        self.target.close.assert_called_once(); self.assertIsNone(app.target)
        self.assertEqual(str(app.install_button.cget('state')), 'disabled')

    def test_check_then_explicit_consent_install_and_completion(self):
        app = self.app
        with patch.object(self.module, 'Deployment', return_value=self.target), \
                patch.object(self.module, 'verify_payload') as digest, \
                patch.object(self.module.threading, 'Thread', side_effect=self.run_worker):
            app.check_button.invoke()
            self.assertTrue(app.busy); self.assertEqual(str(app.entry.cget('state')), 'disabled')
            self.assertEqual(str(app.install_button.cget('state')), 'disabled')
            digest.assert_called_once(); self.target.check.assert_called_once()
            app.drain(); self.assertFalse(app.busy)
            self.assertEqual(str(app.install_button.cget('state')), 'normal')
            self.dialogs.askokcancel.return_value = False
            app.install_button.invoke(); self.target.install.assert_not_called()
            self.assertIn('SHA256:verified', self.dialogs.askokcancel.call_args.args[1])
            self.dialogs.askokcancel.return_value = True
            app.install_button.invoke(); self.target.install.assert_called_once()
            self.assertTrue(app.busy)
            app.drain(); self.assertFalse(app.busy); self.assertIsNone(app.target)
            self.assertEqual(str(app.install_button.cget('state')), 'disabled')
            self.assertIn('ready', (getattr(app, 'status_heading', app.status).get()).lower())

    def test_failed_worker_keeps_actionable_log_and_requires_new_check(self):
        app = self.app
        app.target = self.target
        with patch.object(self.module.threading, 'Thread', side_effect=self.run_worker):
            app.start(Mock(side_effect=RuntimeError('checksum failure')), 'checked')
        app.emit('last diagnostic\n'); app.drain()
        self.assertFalse(app.busy); self.assertIsNone(app.target)
        self.target.close.assert_called_once()
        self.dialogs.showerror.assert_called_once()
        self.assertIn('checksum failure', self.dialogs.showerror.call_args.args[1])
        self.assertIn('last diagnostic', app.output.get('1.0', 'end'))
        log = getattr(app, 'log_file', getattr(app, 'log', None))
        self.assertIn('last diagnostic', Path(log.name).read_text(encoding='utf-8'))
        self.assertEqual(str(app.install_button.cget('state')), 'disabled')

    def test_target_constructor_failure_does_not_start_worker(self):
        with patch.object(self.module, 'Deployment', side_effect=ValueError('bad address')), \
                patch.object(self.app, 'start') as start:
            self.app.check(); start.assert_not_called()
        self.dialogs.showerror.assert_called_once(); self.assertFalse(self.app.busy)

    def test_busy_close_preserves_worker_idle_close_releases_resources(self):
        app = self.app; app.target = self.target; app.busy = True
        with patch.object(app, 'destroy') as destroy:
            app.close(); destroy.assert_not_called(); self.target.close.assert_not_called()
            self.dialogs.showinfo.assert_called_once()
            app.busy = False; app.close(); destroy.assert_called_once(); self.target.close.assert_called_once()
        self.assertTrue(getattr(app, 'log_file', getattr(app, 'log', None)).closed)
