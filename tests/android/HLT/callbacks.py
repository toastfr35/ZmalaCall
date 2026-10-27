# @test A-HLT-008
# @requirements HLR-AND-HISTORY-001
# @environment hardware
# @plan Enroll an Android phone and Pi terminal in a shared group. Miss incoming calls while
# the app is open and closed; reopen and inspect count and contact. Clear the count, answer a
# call and ensure it does not add a miss. Request callback for an offline peer and after an
# unanswered call. Inspect the request on the other device, reconnect and complete a call.
# Restart the app between cases and remove shared permissions before repeating a request.
# Target the app with a terminal callback while open and closed. Inspect the ordinary requester
# notification, tap to the contact without dialing, dismiss/replay, then cancel, complete or expire
# the request. Disable its channel and repeat; re-enable it and refresh. Repeat after enrollment change.
# @pass Missed icons/counts persist without duplicate push/native increments. Incoming and sent
# request icons match the server, duplicate requests remain single, connected calls remove the
# pending pair and clear missed counts, and forbidden contacts cannot receive new requests.
# Callback notifications name only permitted incoming requesters, deduplicate and disappear on
# state changes; tapping opens the contact and preserves an existing call.
"""Cross-device callback qualification; automated state/API tests do not prove hardware delivery."""
if __name__ == '__main__':
    raise SystemExit('Manual hardware qualification required; this plan does not report PASS.')
