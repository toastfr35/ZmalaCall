# @test T-HLT-048
# @requirements HLR-TERM-START-001
# @environment portable
# @plan On Linux, run a copied stable boot helper in a subprocess against real transaction records and an isolated Plymouth command double. Exercise initial boot, interrupted trial, rollback and successful confirmation; compare emitted labels with the durable recovery target. This checks metadata-to-command integration only; inspect actual Plymouth placement and readability on a Pi separately.
# @pass Each subprocess exits successfully and emits exactly the confirmed version through the Plymouth command boundary. A missing daemon also permits exit. Windows skips the Linux executable fixture; neither a skip nor this command double qualifies TV rendering.

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from zmala_terminal.linux.update_transaction import Transactions


@unittest.skipUnless(sys.platform == 'linux', 'Linux Plymouth executable boundary')
class BootVersionIntegrationTests(unittest.TestCase):
    def test_boot_label_tracks_durable_confirmation_across_trial_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tx = Transactions(root/'updates')
            for name, version in (('first', '1.2.3'), ('next', '1.2.4')):
                slot = tx.slots/name; slot.mkdir()
                (slot/'update-release.json').write_text(json.dumps({'version': version}))
            stable = root/'host'; stable.mkdir()
            source = Path(__file__).resolve().parents[3]/'build_tools/linux/boot-version.py'
            shutil.copyfile(source, stable/'boot-version.py')
            capture = root/'captured.json'
            command = root/'plymouth'
            command.write_text('#!'+sys.executable+'\nimport json, os, sys\n'
                               'from pathlib import Path\n'
                               'Path(os.environ["BOOT_VERSION_CAPTURE"]).write_text(json.dumps(sys.argv[1:]))\n')
            command.chmod(0o755)
            environment = dict(os.environ, PATH=str(root)+os.pathsep+os.environ['PATH'],
                               BOOT_VERSION_CAPTURE=str(capture))
            code = ('import runpy,sys; from pathlib import Path; '
                    'runpy.run_path(sys.argv[1])["main"](Path(sys.argv[2]))')

            def check(version):
                subprocess.run([sys.executable, '-c', code, str(stable/'boot-version.py'), str(tx.root)],
                               env=environment, check=True, capture_output=True, text=True, timeout=5)
                self.assertEqual(json.loads(capture.read_text()),
                                 ['display-message', '--text=Zmala v'+version])

            tx.initialize('first'); check('1.2.3')
            tx.prepare('next'); tx.trial(); check('1.2.3')
            tx.recover(); check('1.2.3')
            tx.prepare('next'); trial = tx.trial(); tx.confirm(trial); check('1.2.4')
            command.write_text('#!/bin/sh\nexit 1\n'); capture.unlink()
            subprocess.run([sys.executable, '-c', code, str(stable/'boot-version.py'), str(tx.root)],
                           env=environment, check=True, capture_output=True, text=True, timeout=5)
            self.assertFalse(capture.exists())
