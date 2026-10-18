# @test T-LLT-047
# @requirements LLR-TERM-MAINT-014, LLR-TERM-MAINT-015, LLR-TERM-MAINT-016
# @environment portable
# @plan Feed bounded leased jobs through a stopped-thread polling agent and fake subprocesses; assert three-second polling, single execution and lease reporting, supported POSIX shells, noninteractive working directory, timeout/cancellation cleanup and process-group ownership checks. Stop the agent and check its shared cancellation signal prevents new polling. Drive real bounded output readers with fake child pipes and process-group assignment failure; assert truncation, exit status, ownership and cleanup.
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
    def test_stop_signals_job_cancellation_and_prevents_further_polling(self):
        configuration = Mock()
        with patch.object(maintenance.threading, 'Thread'):
            agent = maintenance.MaintenanceAgent(configuration)
        cancellation = agent.cancelled
        self.assertFalse(cancellation.is_set())
        agent.stop()
        agent.stop()
        self.assertIs(agent.cancelled, cancellation)
        self.assertTrue(cancellation.is_set())
        agent.loop()
        configuration.request.assert_not_called()

    def test_completed_failed_and_unowned_child_results_remain_bounded(self):
        for exit_code in (0, 23):
            process = Mock(stdout=io.BytesIO(b'x'*70000), stderr=io.BytesIO(b'error'), returncode=exit_code)
            process.poll.side_effect = [None, exit_code, exit_code]
            event = Mock(); event.is_set.return_value = False
            with patch.object(maintenance, 'WINDOWS', False), patch('zmala_terminal.linux.commands.shutil.which', return_value='/bin/sh'), \
                    patch.object(maintenance.subprocess, 'Popen', return_value=process), patch.object(maintenance, 'ProcessJob') as job:
                result = maintenance.run_command('unit', 5, event, 'sh')
            self.assertEqual(result['status'], 'completed' if exit_code == 0 else 'failed')
            self.assertEqual(result['exit_code'], exit_code)
            self.assertTrue(result['truncated'])
            self.assertLessEqual(len(result['stdout'])+len(result['stderr']), 65536)
            event.wait.assert_called_once_with(.1)
            job.return_value.close.assert_called()
        process = Mock(); process.poll.return_value = None
        with patch.object(maintenance, 'command_arguments', return_value=['unit']), \
                patch.object(maintenance.subprocess, 'Popen', return_value=process), patch.object(maintenance, 'ProcessJob') as job:
            job.return_value.assign.side_effect = RuntimeError('not our group')
            result = maintenance.run_command('unit', 5, threading.Event(), 'sh')
        process.kill.assert_called_once()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('not our group', result['stderr'])
        self.assertTrue(job.return_value.close.called)

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
