# Isolated network lab

This fixture runs the actual server and shared terminal Engine in disposable
Docker containers. Two home routers and a server router sit between three LANs
and a simulated Internet bridge. No container port is published to the PC or
the real LAN. Credentials are generated for the lab; live server data is not
part of the image build context. Run only on the dedicated WSL Docker daemon.

From the repository root in Ubuntu WSL, as root:

```sh
python3 tests/support/network_lab/lab.py build
python3 tests/adhoc/network_tls.py
ZMALA_LAB_TLS=1 python3 tests/support/network_lab/lab.py down
```

The final command removes the lab containers, networks, credentials and host
bridge rules. Keep WSL running until a test finishes. Concurrent scenario runs
use an exclusive lock. Results are written under `tests/coverage/network-lab/`.
The TLS experiment is ad-hoc and is **not product requirement coverage**.
It does not change installed Pis or enable production fallback.

## TLS prototype

The overlay provides HTTPS configuration at `10.231.100.15:443`, SIP TLS at
`10.231.100.13:443`, and authenticated TURN TLS at `10.231.100.14:443`.
It uses a disposable CA, verifies server certificates, and requires SRTP.
SDES keys travel in TLS-protected SIP. This is not a claim of end-to-end
encryption against the signalling server.

The lab-only server adapter preserves ICE SDP instead of passing it through
the production UDP relay. SIP authentication and terminal call proofs remain
active. Production relay source-address checks are not relaxed. The terminal
adapter enables ICE, TURN TLS and mandatory SRTP, including the explicit
outgoing-call encryption setting. The matrix blocks UDP before established-flow
acceptance at A, B, and both homes, calls in both directions, checks firewall
counters, and verifies fresh decoded H.264 frames and the opposite audio tone.
HTTPS configuration must still load. All media control executes on the SDK
owner thread. WAV files are removed before each recording to prevent stale
audio from satisfying a later test.

## SDK correction under test

The Debian Trixie SDK uses mediastreamer2 5.3.105. Its TURN TCP parser can retain
ChannelData padding on a fragmented packet and read an incomplete header.
Extra bytes invalidate SRTP authentication. `turn-framing.patch` accumulates
input until a complete frame is available and removes padding consistently.
The image fetches the two upstream source files using pinned SHA-256 hashes,
builds a lab-only shared override, and leaves the installed SDK files intact.
The upstream source retains its AGPL-3.0-or-later licence; see
[mediastreamer2 5.3.105](https://github.com/BelledonneCommunications/mediastreamer2/tree/5.3.105).

`tests/adhoc/turn_parser.cpp` checks fragmented headers, padding, coalesced frames and
every input chunk size. The build requires the original parser to fail and the
patched parser to pass. Evidence is stored in `/opt/zmala-lab/parser-results.json`.
This is an SDK experiment, not an installer dependency or a production patch.

## Limits and next steps

The camera is a static 640×480 image, normally about one frame per second.
Audio is generated; Xvfb replaces the TV. OpenH264 replaces the Pi V4L2 encoder;
the production FFmpeg decoder is used. The fixture requests keyframes after
ICE negotiation. It does not establish Pi performance or moving-image quality.

Before production use: qualify the SDK correction on ARM, add server-managed
transport configuration and automatic selection, issue short-lived TURN
credentials, deploy trusted certificates and public routing, test trust/auth
failures, and qualify reconnects, long calls and restricted HTTP proxies.
TCP 443 alone does not guarantee passage through an HTTPS-only proxy or TLS
inspection. Do not describe this experiment as deployed automatic fallback.
Numeric addresses avoid DNS in this lab; endpoint resolution on a network
that also blocks ordinary DNS still needs qualification.
