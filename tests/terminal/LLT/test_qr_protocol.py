# @test T-LLT-060
# @requirements LLR-TERM-SETUP-027, LLR-TERM-SETUP-028
# @environment portable
# @plan Stub child processes, job ownership, file descriptors and worker threads while executing the real QR parent/worker protocol. Send valid, malformed and wrong-shaped JSON; only string QR events may reach the UI thread. Check worker crash diagnostics, spawn/assignment cleanup, static-image restrictions, stop/EOF controls and scanner/output cleanup on worker failures.
# @pass No raw SDK output reaches the decoded-message pipe, malformed messages do not terminate its reader, and all acquired process/scanner/log resources are closed without starting a real child or camera.
import io
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from zmala_terminal.common import qr_scanner, qr_worker


class QRProtocolTests(unittest.TestCase):
    def test_reader_ignores_invalid_messages_and_delivers_only_on_ui_iteration(self):
        with patch.object(qr_scanner,'journal_logging',return_value=True), \
                patch.object(qr_scanner,'ProcessJob'), patch.object(qr_scanner.threading,'Thread'), \
                patch.object(qr_scanner.subprocess,'Popen') as popen:
            process=popen.return_value; process.poll.return_value=None
            process.stdout=io.BytesIO(b'not json\nnull\n[]\n42\n{"type":"qr","value":7}\n{"type":"other","value":"bad"}\n{"type":"qr","value":"hello"}\n')
            callback=Mock(); scanner=qr_scanner.QRScanner(callback,101,'setup',camera='C20',static_picture='test.png')
            args=popen.call_args.args[0]
            self.assertEqual(args[-4:],['--camera','C20','--image','test.png'])
            scanner.read_events(); callback.assert_not_called()
            self.assertTrue(process.stdout.closed)
            scanner.iterate(); callback.assert_called_once_with('hello')
            process.poll.return_value=2
            with self.assertRaisesRegex(RuntimeError,'journalctl'): scanner.iterate()
            scanner.close(); scanner.iterate(); callback.assert_called_once()

    def test_spawn_and_job_assignment_failure_close_private_logs_and_child(self):
        for failed in ('spawn','assign'):
            with self.subTest(failed=failed), patch.object(qr_scanner,'journal_logging',return_value=False), \
                    patch.object(qr_scanner,'ProcessJob') as job, patch.object(qr_scanner.subprocess,'Popen') as popen, \
                    patch.object(qr_scanner.ROOT.__class__,'open',return_value=io.BytesIO()) as opening:
                if failed=='spawn': popen.side_effect=OSError('spawn failed')
                else:
                    job.return_value.assign.side_effect=OSError('job failed')
                    popen.return_value.poll.return_value=None
                with self.assertRaises(OSError): qr_scanner.QRScanner(Mock())
                job.return_value.close.assert_called_once(); self.assertTrue(opening.return_value.closed)
                if failed=='assign':
                    popen.return_value.kill.assert_called_once(); popen.return_value.wait.assert_called_once_with(timeout=5)

    def run_worker(self, image=False, camera='StaticImage: Static picture', failure=None, control=None):
        stopped=threading.Event(); output=Mock(); scanner=Mock(); values=[]; worker=[]
        def create(callback,*args):
            values.append((callback,args)); return scanner
        def iterate():
            values[0][0]('café'); stopped.set()
            if failure: raise failure
        scanner.iterate.side_effect=iterate
        def thread(**kwargs):
            worker.append(kwargs['target']); return Mock()
        args=['qr_worker','--window','101','--profile','setup','--camera',camera]
        if image: args+=['--image','picture.png']
        with patch.dict(sys.modules,{'zmala_terminal.common.native_qr':SimpleNamespace(NativeQRScanner=create)}), \
                patch.object(sys,'argv',args), patch.object(qr_worker.os,'dup',return_value=7), \
                patch.object(qr_worker.os,'dup2') as dup, patch.object(qr_worker.os,'fdopen',return_value=output), \
                patch.object(qr_worker.threading,'Event',return_value=stopped), patch.object(qr_worker.threading,'Thread',side_effect=thread), \
                patch.object(qr_worker.time,'sleep'), patch.object(sys,'stdin',SimpleNamespace(buffer=io.BytesIO(control or b''))):
            try: qr_worker.run()
            except (RuntimeError,ValueError):
                if not failure and not (image and camera!='StaticImage: Static picture'): raise
            dup.assert_called_once_with(2,1)
            worker[0](); self.assertTrue(stopped.is_set())
        scanner.close.assert_called_once(); output.close.assert_called_once()
        return scanner,output

    def test_worker_decoded_json_static_image_stop_and_eof(self):
        for control in (b'ignored\nstop\n',b''):
            scanner,output=self.run_worker(image=True,control=control)
            scanner.set_static_picture.assert_called_once_with('picture.png')
            output.write.assert_called_once_with('{"type": "qr", "value": "caf\\u00e9"}\n')

    def test_worker_capture_error_and_invalid_image_mode_release_resources(self):
        self.run_worker(failure=RuntimeError('camera failed'))
        scanner,output=self.run_worker(image=True,camera='C20')
        scanner.iterate.assert_not_called(); output.write.assert_not_called()
