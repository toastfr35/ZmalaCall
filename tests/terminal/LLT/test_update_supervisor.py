# @test T-LLT-094
# @requirements LLR-TERM-MAINT-026
# @environment portable
# @plan Supply deterministic clocks and operation doubles for waiting, healthy, failed, restarted and timed-out trials. Inspect overlay/stop/start/selection/confirmation ordering, rollback, failed recovery and confirmation I/O failure.
# @pass No lease means no activation; only stable same-process readiness confirms. Failed candidates select the confirmed release; failed recovery retains an error and post-confirmation I/O errors are not reinterpreted as candidate failure.
from unittest.mock import Mock
import unittest
from zmala_terminal.linux.update_supervisor import TrialSupervisor
from zmala_terminal.linux.update_transaction import RecoveryError

class SupervisorTests(unittest.TestCase):
    def run_trial(self, health, lease='lease'):
        now=[0]
        def sleep(delay):now[0]+=delay
        transactions=Mock();transactions.trial.return_value='ticket';transactions.read.return_value={'state':'trial'}
        operations=Mock();operations.claim.return_value=lease;operations.health.side_effect=health
        owner=TrialSupervisor(transactions,operations,lambda:now[0],sleep,deadline=5,stable=2)
        return owner,transactions,operations

    def test_waiting_and_stable_confirmation(self):
        owner,t,o=self.run_trial(lambda:{},None)
        self.assertEqual(owner.activate(),'waiting');t.trial.assert_not_called();o.stop.assert_not_called()
        owner,t,o=self.run_trial(lambda:{'ready':True,'pid':123,'generation':'new'})
        self.assertEqual(owner.activate(),'confirmed');t.confirm.assert_called_once_with('ticket')
        o.display.assert_any_call('updating');o.display.assert_any_call('checking');o.finish.assert_called_once_with('lease')
        self.assertEqual(o.stop.call_count,1);t.recover.assert_not_called()

    def test_failed_or_restarted_trial_rolls_back(self):
        for failure in ('failed','timeout','restart'):
            count=[0]
            def health():
                count[0]+=1
                if o.start.call_count>1:return {'ready':True,'pid':99,'generation':'old'}
                if failure=='failed':return {'failed':True}
                if failure=='timeout':return {'ready':False}
                return {'ready':True,'pid':count[0],'generation':'new'}
            owner,t,o=self.run_trial(health)
            self.assertEqual(owner.activate(),'rolled_back');t.confirm.assert_not_called();t.recover.assert_called_once()
            o.finish.assert_called_once_with('lease');self.assertEqual(o.start.call_count,2)

    def test_failed_recovery_and_confirmation_write_failure_do_not_clear_overlay(self):
        owner,t,o=self.run_trial(lambda:{'failed':True})
        with self.assertRaises(RecoveryError):owner.activate()
        o.finish.assert_not_called();o.display.assert_any_call('recovery_failed')
        owner,t,o=self.run_trial(lambda:{'ready':True,'pid':1,'generation':'new'})
        t.confirm.side_effect=OSError('disk failure')
        with self.assertRaises(OSError):owner.activate()
        t.recover.assert_not_called();o.finish.assert_not_called()
