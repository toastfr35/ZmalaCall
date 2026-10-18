# @test T-LLT-052
# @requirements LLR-TERM-START-005
# @environment portable
# @plan Inject launcher locks and PID observations to reject concurrent source profiles and reused processes; inspect the installed service control-group cleanup policy without changing services.
# @pass A duplicate profile or reused PID never launches or kills an unrelated process; service cleanup owns its control group.

import configparser
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.support.linux_units import ROOT, load

launcher = load('launcher')


class ApplianceInstallTests(unittest.TestCase):
    def test_profile_lock_refuses_second_instance_before_running_app(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(launcher, 'ROOT', Path(folder)), \
                patch.dict(os.environ, {'ZMALA_RUNTIME_DIR':folder}), patch.object(sys, 'argv', ['launcher','run','--profile','fixture']), \
                patch.object(launcher.fcntl, 'flock', side_effect=BlockingIOError), patch.object(launcher.runpy, 'run_path') as run, \
                patch.object(launcher.os, 'umask'):
            with self.assertRaises(SystemExit):
                launcher.main()
            run.assert_not_called()

    def test_stop_does_not_signal_reused_pid(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(launcher, 'ROOT', Path(folder)), \
                patch.dict(os.environ, {'ZMALA_RUNTIME_DIR':folder}), patch.object(sys, 'argv', ['launcher','stop','--profile','fixture']), \
                patch.object(launcher, 'start_time', return_value='new-start'), \
                patch.object(launcher.os, 'killpg', create=True) as kill, patch.object(launcher.os, 'umask'):
            record = Path(folder)/'fixture.pid.json'
            record.write_text(json.dumps({'pid':123,'started':'old-start'}))
            launcher.main()
            kill.assert_not_called(); self.assertFalse(record.exists())
        unit = configparser.ConfigParser(strict=False, interpolation=None)
        unit.read(ROOT/'build_tools/linux/zmalacall-terminal.service')
        self.assertEqual(unit['Service']['KillMode'], 'control-group')
