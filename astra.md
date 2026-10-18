# Remaining review work

Reviewed against `db25e2e` on 18 October 2026. This file contains only outstanding
improvements and acceptance gaps. Completed fixes and superseded test records
are available in Git history. These items are source-supported risks or
optimization opportunities, not claims of newly reproduced production failures.

## High priority

### Recover interrupted identity changes and older backups

Account and device changes span independently written configuration, callback,
console and bootstrap files. The barriers in
[`admin-routes.js`](zmala_server/http/admin-routes.js) wait for writes but do not
make them transactional; [`snapshot-file.js`](zmala_server/snapshot-file.js)
does not provide fsync durability. Add deterministic startup reconciliation or
a transaction journal, and define restore epochs without weakening terminal
revision rollback protection. Inject crashes at every write boundary and verify
device credentials, command ownership and callbacks after restart. Until then,
retain the [documented backup/re-enrollment procedure](docs/server.md#persistence-and-backup).

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

### Refine administration conflicts and controller interfaces

Browser editors now submit revisions and stale writes are rejected. Revisions
are global and optional for older API callers. Consider narrower conflict scopes
and an explicit compatibility policy for unversioned writes, with concurrent-edit
tests that preserve newer values. For terminal controller refactors, introduce
explicit host interfaces only where they clarify actual dependencies; keep state
ownership in `Terminal` and avoid a wholesale rewrite without a demonstrated need.
