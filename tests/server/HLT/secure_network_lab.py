# @test S-HLT-030
# @requirements HLR-SRV-MEDIA-014
# @environment linux-root
# @plan Run the real secure server and two real native terminal Engines in the isolated Docker network lab. Block forwarded UDP at A, B, both, or neither. Verify HTTPS configuration, authenticated SIP TLS, TURN credentials, SRTP/relay ICE, decoded opposite audio tones and fresh H.264 frames in both call directions. Check drop counters, repeated calls and hangup. Probe endpoint certificate trust and native SIP rejection of an untrusted CA or wrong certificate name. Synthetic static cameras do not qualify Pi motion performance or institutional HTTP proxies.
# @pass All eight calls sustain decoded audio/video; TLS certificate probes and firewall checks pass. No production transport monkeypatch is permitted.
from tests.support.network_lab.tls_scenarios import main

if __name__ == '__main__':
    main()
