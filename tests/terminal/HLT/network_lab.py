# @test T-HLT-032
# @requirements HLR-TERM-CALL-009, HLR-TERM-CALL-010
# @environment linux-root
# @plan Run the shared Docker NAT lab with the real terminal Engine, its server proof checks, Liblinphone and production decoder. Replace physical camera/audio, Pi V4L2 encoding and UI control with generated media, OpenH264 software encoding and queued commands. Exercise outgoing, authenticated incoming, hangup, idle incoming and firewall recovery; inspect decoded opposite audio tones and video frame progress. The scenario is shared with S-HLT-029. With --udp-blocked, block all forwarded UDP before fresh registration at each home gateway, verify HTTP still works and calls fail in both directions, then separately block RTP/RTCP and verify connected SIP with no decoded media. Remove each fault and require a successful recovery call. Observe firewall drop counters; these are bounded negative tests of the current UDP-only configuration.
# @pass Calls start, accept a valid server proof, deliver decoded media and return to idle on both clients. No claim is made for user-facing countdown/UI, invalid-proof rejection, Pi hardware performance or arbitrary external networks; those require their separate tests.

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tests.support.network_lab.scenarios import run

if __name__ == '__main__':
    run(udp_blocked="--udp-blocked" in sys.argv[1:])
