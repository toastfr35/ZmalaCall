# @test A-HLT-007
# @requirements HLR-AND-UPDATE-001
# @environment hardware
# @plan On disposable Android 10 and Android 12+ devices, install a release-signed updater APK
# and enroll a fixture account. Publish or inject a test-only transport for a higher-version
# same-key APK. Check manual Update/Later, installation permission, opted-in automatic updates,
# approval fallback and enrollment retention. Attempt updating while a real call rings and is
# connected, then during transfer; calls must continue and transfer/commit must wait. Inspect
# the version on contacts and its absence on welcome and call screens. Include a corrupt APK,
# wrong signing key, failed download, metered network and process restart.
# @pass Observed cases have exact evidence for version, retained enrollment, no call interruption,
# approval on Android 10, automatic install or handled Android approval on Android 12+, and
# rejection of corrupt/wrong-key APKs. A printed plan or skipped device case is not a passed run.
"""Physical update qualification plan; run the device fixture for installer integration separately."""
if __name__ == '__main__':
    raise SystemExit('Manual hardware qualification required; this plan does not report PASS.')
