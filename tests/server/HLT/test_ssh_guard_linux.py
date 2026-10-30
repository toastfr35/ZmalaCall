# @test S-HLT-022
# @requirements HLR-SRV-HOST-001, HLR-SRV-HOST-006
# @environment linux-root
# @plan Create isolated Linux network namespaces with Ethernet and Wi-Fi interfaces, apply the real nftables guards twice and attempt IPv4/IPv6 connections; assert ordinary SSH accepts only wired local-subnet sources, reject routed non-local sources and Wi-Fi ingress to the Ethernet address, keep the separate developer tunnel endpoint reachable, then destroy every fixture.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

from tests.support import ssh_guard_namespace


class FirewallTests(ssh_guard_namespace.GuardScenario):
    """Run the shared host policy against this component's requirement."""


class DeveloperSubnetTests(ssh_guard_namespace.GuardScenario):
    """Ordinary SSH is local-only; tunnel-only SSH remains separately reachable."""

    developer_subnets = True
