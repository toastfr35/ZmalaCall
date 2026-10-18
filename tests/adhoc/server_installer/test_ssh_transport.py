# Installer regression tests; outside the Pi runtime requirements baseline.
import unittest
from build_tools.server_installer.backend import Deployment
from tests.support.ssh_deployment import SSHContract


class ServerSSHTests(SSHContract, unittest.TestCase):
    deployment_class = Deployment
