# Local SIP transport patch

This directory contains the runtime files from the npm `sip@0.0.6` release,
maintained upstream at https://github.com/kirm/sip.js. The upstream MIT license
is retained in `LICENSE`. `SHA256SUMS.upstream` records the original files before
our changes. The npm release integrity was:

```
sha512-t+FYic4EQ25GTsIRWFVvsq+GmVkoZhrcoghANlnN6CsWMHGcfjPDYMD+nTBNrHR/WnRykF4nqx4i+gahAnW5NA==
```

The original runtime patch is in `sip.js`, inside `exports.create`: the optional
`options.requestGuard(message, remote)` runs before transaction lookup or
creation. Returning zero permits processing; a nonzero SIP status sends a
stateless rejection to the received transport flow and bypasses the cache.
ZmalaCall uses this only for CANCEL, matching the dialog peer, From tag, CSeq
and Via branch. Rejected cancellation cannot poison a later legitimate CANCEL
transaction. The caller may receive a repeated stateless rejection on retry.

The stream parser additionally requires one finite, unsigned integer
Content-Length (including compact `l`), bounds headers/body, and closes an
unfinished message after 30 seconds. Duplicate lengths are rejected. CRLF
keepalives between messages and pipelining remain supported; transport closure
clears the parser deadline. `tests/sip-bounds.test.js` covers malformed lengths,
fragments, keepalives and the absolute body deadline.

`proxy.js` bypasses response contexts for ACK, caps outstanding contexts at 128
per transport/IP and 2048 globally, expires contexts after 90 seconds, and clears
them on shutdown. Context limits count signalling IPs, so devices behind one NAT
share the quota. These limits bound proxy metadata, not every underlying SIP
transaction or incoming connection. The same test covers ACK bursts, quotas and
expiry without binding live ports.

The application adapter is `../../sip-transport.js`. Normal routing, Digest,
UDP/TCP, retransmissions, media relay and the existing Max-Forwards workaround
remain in their original layers. The package metadata adds a local version,
private flag and license field and omits the upstream test script/development
dependency (the upstream test suite is not shipped); the WebSocket dependency
is unchanged.

The server installs this as `file:vendor/sip`, including with `npm ci
--ignore-scripts`; no postinstall patching or edits to installed dependencies
are needed. Application lint/format checks exclude these third-party files.
`tests/sip-cancel-wire.test.js` exercises the patch over real UDP, including a
forged CANCEL followed by the legitimate cancellation on the same transaction.

When updating upstream, compare these files to the recorded originals, reapply
all local changes deliberately, update the package version/provenance and run all server
tests. This patch does not establish complete RFC compliance or make the server
ready for public Internet exposure.
