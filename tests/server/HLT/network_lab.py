# @test S-HLT-029
# @requirements HLR-SRV-CALL-001, HLR-SRV-CALL-002, HLR-SRV-MEDIA-007
# @environment linux-root
# @plan Start the disposable Docker three-LAN fixture. Use actual server and two shared terminal Engines with synthetic media and OpenH264 software encoding in place of Pi V4L2 hardware. Register and fetch configuration over NAT, call both ways and after idle, verify decoded opposite tones and H.264 frame progress, inject impairment and a blocked-media fault, and check recovery. Routers translate UDP ports; direct private-server access must fail. This is an opt-in stress environment, not qualification of arbitrary Internet networks. With --udp-blocked, block all forwarded UDP before fresh registration at each home gateway, verify HTTP still works and calls fail in both directions, then separately block RTP/RTCP and verify connected SIP with no decoded media. Remove each fault and require a successful recovery call. Observe firewall drop counters; these are bounded negative tests of the current UDP-only configuration.
# @pass Both authenticated call directions carry decoded media and release on hangup; impairment retains media; blocked media is detected independently of successful SIP signalling; a later call recovers. Physical C20, TV, Bluetooth, security of public exposure and every NAT type remain outside this run.

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tests.support.network_lab.scenarios import run

if __name__ == '__main__':
    run(udp_blocked="--udp-blocked" in sys.argv[1:])
