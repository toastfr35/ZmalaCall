# @test T-HLT-033
# @requirements HLR-TERM-COM-009
# @environment linux-root
# @plan Run the shared secure-network matrix against the actual terminal Engine with its server-provided TLS/TURN policy. Verify native SRTP and relay state plus decoded peer media while UDP is denied at each home, in both directions. Use synthetic media and a disposable CA. Reject an untrusted CA and a wrong certificate name through the native SIP client. Physical Pi load and moving-camera quality are not measured.
# @pass All matrix checks pass, with fresh decoded tones/frames and no transport configuration monkeypatch.
from tests.support.network_lab.tls_scenarios import main

if __name__ == '__main__':
    main()
