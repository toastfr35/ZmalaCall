# @test T-LLT-047
# @requirements LLR-TERM-MAINT-003, LLR-TERM-MAINT-004
# @environment portable
# @plan Feed bounded leased jobs through a stopped-thread polling agent and fake subprocesses; assert three-second polling, single execution and lease reporting, supported POSIX shells, noninteractive working directory, timeout/cancellation cleanup and process-group ownership checks.
# @pass Assertions must reject invalid jobs and foreign process groups, terminate owned groups exactly once and never launch real shell commands.

import io
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from zmala_terminal.common import maintenance
from zmala_terminal.linux.commands import command_arguments
from zmala_terminal.linux.process_job import ProcessJob


class MaintenanceOwnershipTests(unittest.TestCase):
    def test_shell_arguments_are_explicit_and_unsupported_shells_fail(self):
        with patch('zmala_terminal.linux.commands.shutil.which', side_effect=lambda name: '/bin/'+name):
            for shell in ('sh', 'bash'):
                self.assertEqual(command_arguments('echo test', shell), ['/bin/'+shell, '-c', 'echo test'])
            for shell in ('powershell', 'cmd', 'sh -c', ''):
                with self.assertRaises(ValueError):
                    command_arguments('echo test', shell)

    def test_single_lease_is_executed_then_reported_before_next_poll(self):
        with patch.object(maintenance.threading, 'Thread'):
            agent = maintenance.MaintenanceAgent(Mock())
        agent.cancelled = Mock()
        agent.cancelled.is_set.side_effect = [False, False, True]
        job = {'id':'fixture', 'command':'true', 'timeout_seconds':5, 'shell':'sh', 'lease':'lease'}
        agent.configuration.request.return_value = maintenance.json.dumps({'job':job})
        agent.submit = Mock()
        with patch.object(maintenance, 'run_command', return_value={'status':'completed'}) as run:
            agent.loop()
        run.assert_called_once_with('true', 5, agent.cancelled, 'sh')
        agent.submit.assert_called_once_with('fixture', {'status':'completed', 'lease':'lease'})
        agent.cancelled.wait.assert_called_once_with(3)
        for timeout in (4, 121):
            agent.cancelled.is_set.side_effect = [False, False, True]
            agent.configuration.request.return_value = maintenance.json.dumps({'job':job | {'timeout_seconds':timeout}})
            with patch.object(maintenance, 'run_command') as run:
                agent.loop()
                run.assert_not_called()

    def test_owned_process_group_close_is_idempotent_and_rejects_foreign_group(self):
        job = ProcessJob()
        with patch('zmala_terminal.linux.process_job.os.getpgid', create=True, return_value=123), \
                patch('zmala_terminal.linux.process_job.os.killpg', create=True) as kill, \
                patch('zmala_terminal.linux.process_job.signal.SIGKILL', 9, create=True):
            with self.assertRaises(RuntimeError):
                job.assign(SimpleNamespace(pid=999))
            job.close(); kill.assert_not_called()
            job.assign(SimpleNamespace(pid=123)); job.close(); job.close()
            kill.assert_called_once_with(123, 9)

    def test_timeout_and_cancel_close_job_with_noninteractive_isolated_process(self):
        for cancelled_value, expected in ((False, 'timed_out'), (True, 'cancelled')):
            process = Mock(stdout=io.BytesIO(b'output'), stderr=io.BytesIO(b''))
            process.poll.return_value = None
            event = threading.Event()
            if cancelled_value:
                event.set()
            with patch.object(maintenance, 'command_arguments', return_value=['/bin/sh', '-c', 'true']), \
                    patch.object(maintenance.subprocess, 'Popen', return_value=process) as popen, \
                    patch.object(maintenance, 'ProcessJob') as job, \
                    patch.object(maintenance, 'process_options', return_value={'start_new_session':True}), \
                    patch.object(maintenance.time, 'monotonic', side_effect=[0, 10]):
                result = maintenance.run_command('true', 5, event, 'sh')
            self.assertEqual(result['status'], expected)
            self.assertEqual(result['stdout'], 'output')
            self.assertTrue(popen.call_args.kwargs['start_new_session'])
            self.assertEqual(popen.call_args.kwargs['stdin'], maintenance.subprocess.DEVNULL)
            self.assertEqual(popen.call_args.kwargs['cwd'], str(maintenance.ROOT))
            job.return_value.assign.assert_called_once_with(process)
            self.assertTrue(job.return_value.close.called)
