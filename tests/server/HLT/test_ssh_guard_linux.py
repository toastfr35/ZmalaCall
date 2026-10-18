# @test S-HLT-022
# @requirements HLR-SRV-HOST-001
# @environment linux-root
# @plan Create isolated Linux network namespaces with Ethernet and Wi-Fi interfaces, apply the real nftables guard twice and attempt IPv4/IPv6 connections; assert SSH accepts only Ethernet while other service ports remain reachable, also route packets to the Ethernet address through Wi-Fi to test weak-host ingress, then destroy every fixture.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

from tests.support import ssh_guard_namespace


class FirewallTests(ssh_guard_namespace.GuardScenario):
    """Run the shared host policy against this component's requirement."""
