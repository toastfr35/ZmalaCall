# Terminal application update qualification

Status on 3 November 2026: implementation is installed on term2; end-to-end
automatic update and rollback qualification is still in progress. This record
distinguishes executed checks from remaining plans. It contains no device
credentials, account backups or private logs.

| Check | Evidence and result |
| --- | --- |
| Public release identity | Published v0.3.71 has the nine user downloads and two machine assets. Its Ed25519 signature, package digest and commit were checked against the release tag. Passed. |
| Shared server feed | Term2 retrieved the manifest from its enrolled HTTPS server and independently verified its signature. Passed. |
| Native preparation | The published payload compiled the video, audio and TURN corrections in unprivileged isolated systemd units on the Pi. The previously running terminal stayed active. Passed. |
| Native core preflight | A disposable candidate copy instantiated, iterated and closed the real Engine with empty account configuration. PrivateDevices, PrivateNetwork, PrivateTmp, read-only host paths and resource deadlines were applied. Passed. |
| One-time updater bootstrap | A private rollback backup was retained. The signed compiled application passed a stable UI heartbeat before independent updater provisioning. Terminal and updater services are active with zero restarts. Passed. |
| TV at bootstrap | The TV remained off. No TV power or input command was requested for update progress. Passed for this run. |
| Durable transaction/data replay | Automated Linux scenarios kill processes at journal and atomic data-exchange boundaries, then replay recovery. Passed; these are process-death tests, not physical power cuts. |
| Actual automatic signed transition | Planned: publish the next compatible version, allow normal idle activation and inspect confirmed selection, language, enrollment and peripheral state. Not yet run. |
| Failed candidate and supervisor interruption | Planned: controlled diagnostic trials with retained recovery, then verify the confirmed application and settings return. No unsigned diagnostic fixture may enter the public feed or production trust registry. Not yet run. |
| Call admission during maintenance | Automated app-side fences and server-side SIP 480 tests passed. Physical busy-call deferral still needs a suitable call test. |
| Physical power interruption | Not run. Filesystem fsync/rename and process-kill evidence do not prove an SD controller's behavior when power is removed. |

The first server deployment encountered a generated admin bundle mismatch against
older installed authored modules. The retained source backup restored readiness;
an isolated reproduction confirmed the mismatch. Regenerating/checking the bundle
on the Pi before restart resolved deployment. Account data was untouched.

Qualification review also found two continuity gaps: a passive application's next
heartbeat could lose its remembered sleeping-media state, and supervisor restart
could briefly publish idle before retaining recovery fencing. Regression checks
now cover both. Native preflight was strengthened beyond loading shared libraries
because GUI trial startup deliberately postpones normal media initialization.

Operating-system, kernel, firmware and dependency upgrades remain outside this
feature. Signing credentials stay in the release workflow. Future qualification
results must be recorded as executed evidence rather than converting these plans
to passes without a run.
