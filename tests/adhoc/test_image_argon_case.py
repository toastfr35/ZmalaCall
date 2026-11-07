"""Offline image case-selection regressions; physical fan behavior is separate."""
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from zmala_images import application_provision as provision, image_case, project


class ArgonImageTests(unittest.TestCase):
    @staticmethod
    def ledgers():
        return {'passwd': 'root:x:0:0:root:/root:/bin/sh\n', 'group': 'root:x:0:\n',
                'shadow': 'root:!:1:0:99999:7:::\n', 'gshadow': 'root:!::\n'}

    def test_opt_in_is_typed_and_limited_to_terminal_roles(self):
        for role in ('terminal', 'combined', 'server'):
            self.assertFalse(provision.case_selection(role, False))
        for role, value in [('server', True), ('terminal', 1), ('combined', 'true')]:
            with self.assertRaises(ValueError):
                provision.accounts(self.ledgers(), role, value)
        for role in ('terminal', 'combined'):
            groups = provision.accounts(self.ledgers(), role, True)['group']
            row = next(row for row in groups.splitlines() if row.startswith('i2c:'))
            self.assertEqual(row.split(':')[3], 'zmalaterminal')
            self.assertNotIn('i2c:', provision.accounts(self.ledgers(), role)['group'])

    @unittest.skipIf(os.name == 'nt', 'Offline Unix roots require Linux symlinks')
    def test_case_provisioning_and_assembly_agree_for_both_terminal_roles(self):
        names = set(provision.HOST_FILES.values())
        names.update('build_tools/linux/zmalacall-'+name+'.service' for name in
                     ('terminal', 'display', 'pairing', 'cec', 'compositor', 'server'))
        names.update(('build_tools/linux/low-wear-swap.conf', 'build_tools/linux/70-zmalacall-presenter.rules',
                      'zmala_terminal/linux/99-zmalacall-c20.rules'))
        records = {name: ((project.ROOT/name).read_bytes(), False) for name in names}
        for role in ('terminal', 'combined'):
            for selected in (False, True):
                with self.subTest(role=role, selected=selected), tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    (root/'etc').mkdir()
                    for name, body in self.ledgers().items():
                        (root/'etc'/name).write_text(body)
                    units = root/'usr/lib/systemd/system'
                    units.mkdir(parents=True)
                    (units/'NetworkManager.service').write_text('[Service]\nExecStart=/bin/true\n')
                    result = provision.provision(root, records, role, selected)
                    self.assertIs(result['argon_one'], selected)
                    self.assertIs(image_case.selected(root, role), selected)
                    with self.assertRaises(ValueError):
                        image_case.selected(root, 'server')
                    module = root/'etc/modules-load.d/zmala-i2c.conf'
                    self.assertIs(module.exists(), selected)
                    rules = root/'etc/udev/rules.d/99-zmalacall-i2c.rules'
                    self.assertIs(rules.exists(), selected)
                    self.assertIn('ExecStopPost=-/usr/bin/python3 /usr/local/lib/zmalacall-terminal-host/argon_fan.py',
                                  (units/'zmalacall-terminal.service').read_text())
                    if selected:
                        for path in (module, rules, root/'etc/group'):
                            before = path.read_text()
                            path.write_text('')
                            with self.assertRaises(ValueError):
                                image_case.selected(root, role)
                            path.write_text(before)
                    config = root/'etc/zmalacall/terminal.conf'
                    config.write_text('ZMALA_ARGON_ONE_FAN='+str(int(not selected))+'\n')
                    with self.assertRaises(ValueError):
                        image_case.selected(root, role)

    def test_generic_boot_keeps_i2c_unchanged_and_selected_boot_checks_alias(self):
        run = Mock()
        image_case.configure_tree(Path('/root'), Path('/staging'), False, run)
        run.assert_not_called()
        self.assertEqual(image_case.boot_parameters(False), '')
        self.assertEqual(image_case.boot_parameters(True), 'dtparam=i2c_arm=on\n')
        with tempfile.TemporaryDirectory() as folder:
            stage = Path(folder)
            (stage/'board.dtb').write_bytes(b'original')
            (stage/'argon.dtb').write_bytes(b'i2c enabled')
            run.side_effect = [None, SimpleNamespace(stdout='/soc/i2c@7e804000\n'),
                               SimpleNamespace(stdout='okay\n')]
            image_case.configure_tree(Path('/root'), stage, True, run)
            self.assertEqual((stage/'board.dtb').read_bytes(), b'i2c enabled')
            self.assertEqual(run.call_args_list[0].args[0][-2:], ['-', 'i2c_arm=on'])
            self.assertEqual(run.call_args_list[1].args[0][-2:], ['/aliases', 'i2c1'])

    def test_disabled_or_failed_parameter_application_never_replaces_slot_tree(self):
        for failure in ('disabled', 'command'):
            with tempfile.TemporaryDirectory() as folder:
                stage = Path(folder)
                (stage/'board.dtb').write_bytes(b'original')
                (stage/'argon.dtb').write_bytes(b'bad')
                run = Mock(side_effect=(subprocess.CalledProcessError(1, 'dtmerge') if failure == 'command'
                    else [None, SimpleNamespace(stdout='/soc/i2c@7e804000\n'), SimpleNamespace(stdout='disabled\n')]))
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    image_case.configure_tree(Path('/root'), stage, True, run)
                self.assertEqual((stage/'board.dtb').read_bytes(), b'original')


if __name__ == '__main__':
    unittest.main()
