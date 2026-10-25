# @test T-LLT-081
# @requirements LLR-TERM-POWER-010
# @environment portable
# @plan Parse the C20 udev policy's match/assignment clauses and evaluate USB add/bind, changed node, unrelated camera/product and USB-interface fixtures. Require runtime power on only for the C20 USB device. When udevadm is available, validate the rule with its real verifier. These configuration checks do not operate USB hardware or prove physical wake reliability.
# @pass C20 add/bind matches independently of node number; other identities, interfaces and actions do not match. The only assignment disables runtime suspend. Available udev syntax verification succeeds; missing udev is recorded as a skip.
from pathlib import Path
import re
import shutil
import subprocess
import unittest

POLICY = Path(__file__).resolve().parents[3] / 'zmala_terminal/linux/99-zmalacall-c20.rules'


class C20PowerPolicyTests(unittest.TestCase):
    def test_only_c20_device_runtime_suspend_is_disabled(self):
        rules = [line for line in POLICY.read_text().splitlines() if line and not line.startswith('#')]
        self.assertEqual(len(rules), 1)
        clauses = re.findall(r'([A-Z]+(?:\{[^}]+\})?)\s*(==|=)\s*"([^"]*)"', rules[0])
        self.assertEqual(len(clauses), 6)
        matches = [(key, value.split('|')) for key, operator, value in clauses if operator == '==']
        self.assertEqual([(key, value) for key, operator, value in clauses if operator == '='],
                         [('ATTR{power/control}', 'on')])
        device = {'ACTION': 'add', 'SUBSYSTEM': 'usb', 'ENV{DEVTYPE}': 'usb_device',
                  'ATTR{idVendor}': '0525', 'ATTR{idProduct}': 'a4ad'}
        def applies(properties):
            return all(properties.get(key) in values for key, values in matches)
        for action in ('add', 'bind'):
            for node in ('1-1.1', '1-1.4'):
                self.assertTrue(applies(device | {'ACTION': action, 'KERNEL': node}))
        for override in ({'ACTION': 'remove'}, {'ACTION': 'change'}, {'SUBSYSTEM': 'video4linux'},
                         {'ENV{DEVTYPE}': 'usb_interface'}, {'ATTR{idVendor}': '1234'},
                         {'ATTR{idProduct}': 'a4ac'}):
            with self.subTest(override=override):
                self.assertFalse(applies(device | override))

    @unittest.skipUnless(shutil.which('udevadm'), 'udevadm is not installed')
    def test_real_udev_verifier_accepts_policy(self):
        result = subprocess.run(['udevadm', 'verify', str(POLICY)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
