# Remaining review work

Reviewed against `5213c3e` on 18 October 2026. This file contains only outstanding
improvements and acceptance gaps. Completed fixes and superseded test records
are available in Git history. Code-review risks are distinguished from reproduced
hardware failures below.

## High priority

### Recover interrupted identity changes

Account and device changes span independently written configuration, callback,
console and bootstrap files. The barriers in
[`admin-routes.js`](zmala_server/http/admin-routes.js) wait for writes but do not
make them transactional; [`snapshot-file.js`](zmala_server/snapshot-file.js)
does not provide fsync durability. Extend deterministic startup reconciliation or
transaction journals to ordinary identity mutations. Inject crashes at every write
boundary and verify credentials, command ownership and callbacks after restart.
The [supported backup restore](docs/server.md#persistence-and-backup) now has its
own journal, rollback recovery and revision advancement; that transaction does not
cover unrelated account edits.

### Qualify C20 readiness after USB power restoration

On term2 on 18 October, the C20 re-enumerated after hub power restoration and the
terminal reported its devices refreshed. The following call still failed with
UVC probe timeouts (-110), MJPEG format I/O errors and ALSA frequency/open errors.
Stopping the terminal, cycling USB power and restarting recovered a 25-second
call with decoded audio and at least 18.7 received fps at 1080p.

[`media_present()`](zmala_terminal/linux/usb_power.py) checks V4L2 and ALSA
enumeration, which is insufficient to prove capture readiness. Investigate the
device/driver recovery sequence and qualify repeated idle/wake/call cycles;
bound recovery attempts and avoid reporting capture health from enumeration
alone. The single successful recovery does not establish a durable fix.

### Bound native media memory and recovery time

[`codec.c`](zmala_terminal/linux/media/video/codec.c) bounds queue counts and
measures queue age, but lacks queue byte budgets and a frame-age policy. Decoded
dimensions feed image allocation, and shutdown waits on `pthread_join()`.
Add access-unit/decoded-size limits and byte budgets; preserve H.264 reference
frames and keyframe recovery rather than dropping arbitrary compressed packets.
Test oversized inputs, allocation failures, stalled camera/codec shutdown and
repeated reopen failures against the target SDK. Measure RSS, oldest-frame age,
audio continuity and recovery time during sustained Pi calls and USB faults.

## Medium priority

### Verify SIP response correlation and lost-peer recovery

[`sip.js`](zmala_server/vendor/sip/sip.js) selects client transactions by method,
Call-ID and Via branch without an explicit responding-flow check at lookup.
Use isolated UDP/TCP peers to test matching responses from the wrong flow before
changing correlation rules. In [`sip-server.js`](zmala_server/sip-server.js),
connected dialogs expire after four hours of signalling inactivity. Define and
test abandoned-call recovery without terminating valid quiet calls; cover peer
loss, network interruption, media-resource release and subsequent calls.

### Define message deduplication across engine replacement

[`Engine._seen_messages`](zmala_terminal/common/engine.py) is a per-engine set
with arbitrary eviction at 256 entries. Define sender scope and a deduplication
window, then test delayed duplicates across configuration-driven core replacement
and restart. Retain bounded identity metadata outside the core if the chosen
contract requires it.

### Add reference-aware photo and log retention

[`photos.js`](zmala_server/photos.js) and
[`photo_cache.py`](zmala_terminal/common/photo_cache.py) bound active work but
do not garbage-collect unreferenced portrait files. Desktop terminal/QR file logs
also need retention; installed Pi journal limits already exist. Use grace periods
and preserve active references and useful diagnostics. Test concurrent publication,
reset/re-enrollment, cancellation, disk-full errors and restart during cleanup.

### Reduce console-history serialization cost

[`ConsoleJobs.save()`](zmala_server/console-jobs.js) synchronously serializes the
whole history on every mutation. Snapshot coalescing already bounds queued writes;
it does not remove JSON encoding from the SIP event loop. Measure event-loop delay,
mutation latency and memory on the server Pi with realistic retained output and
slow storage. Consider separating immutable output from job metadata, preserving
durable acknowledgements, retry semantics and ownership checks.

### Reuse carousel canvas items

[`ui/carousel.py`](zmala_terminal/common/ui/carousel.py) creates replacement
canvas items and deletes the previous set during redraws. Incremental updates may
reduce allocations; render-cache byte budgets are already implemented. Require
equivalent selection, names, badges and animation output, then compare Pi p95/p99
frame times and RSS for three/five portraits, long names and language changes.

### Qualify shutdown and descendant cleanup

[`QRScanner.close()`](zmala_terminal/common/qr_scanner.py) synchronously waits for
process/thread shutdown. [`MaintenanceAgent.stop()`](zmala_terminal/common/maintenance.py)
signals cancellation without joining its worker. Measure worst-case UI blocking
and test timeout, immediate exit and session-detaching children. Define standalone
Linux cleanup guarantees separately from systemd control-group cleanup. Any
asynchronous teardown must release the camera before the call core acquires it
and preserve native SDK thread ownership.

### Complete release rollback and hardware acceptance

The [Linux installers](build_tools/linux/) already use release directories,
checksums and service checks; server startup failure can restore the prior
application release. Add a versioned release manifest and test interrupted
upgrades, data/schema compatibility and backup restoration, including failures
after dependency or configuration changes. Verify enrollment, registration and a
real call rather than service liveness alone. Continue physical qualification for
repeated calls after idle, USB reconnect/power cycles, sustained media, TV models
and button/label usability at TV distance. Portable tests and earlier short calls
do not establish those results for every supported setup.

## Lower priority

### Close requirement-based verification gaps

Every server and Pi terminal LLR now has direct LLT verification plans; the
validator rejects unmapped LLRs. Use `requirements/output/tests.html` to
prioritize the remaining unmapped HLR system scenarios and review partial
assertions against the full requirements. Unit links and passing component
checks do not replace physical qualification. In
particular, qualify startup/deployment failure recovery and TV/USB behavior on
physical devices. Record the test ID, revision, platform, outcome and skipped or
manual observations; do not treat a plan, portable pass or skip as hardware
acceptance. Keep the matrix generated from comments and Doorstop references.

### Refine administration conflicts and controller interfaces

Browser editors now submit revisions and stale writes are rejected. Revisions
are global and optional for older API callers. Consider narrower conflict scopes
and an explicit compatibility policy for unversioned writes, with concurrent-edit
tests that preserve newer values. For terminal controller refactors, introduce
explicit host interfaces only where they clarify actual dependencies; keep state
ownership in `Terminal` and avoid a wholesale rewrite without a demonstrated need.
