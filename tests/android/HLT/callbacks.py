# @test A-HLT-008
# @requirements HLR-AND-HISTORY-001
# @environment hardware
# @plan Enroll an Android phone and Pi terminal in a shared group. Miss incoming calls while
# the app is open and closed; reopen and inspect count and contact. Clear the count, answer a
# call and ensure it does not add a miss. Request callback for an offline peer and after an
# unanswered call. Inspect the request on the other device, reconnect and complete a call.
# Restart the app between cases and remove shared permissions before repeating a request.
# @pass Missed icons/counts persist without duplicate push/native increments. Incoming and sent
# request icons match the server, duplicate requests remain single, connected calls remove the
# pending pair and clear missed counts, and forbidden contacts cannot receive new requests.
"""Cross-device callback qualification; automated state/API tests do not prove hardware delivery."""
if __name__ == '__main__':
    raise SystemExit('Manual hardware qualification required; this plan does not report PASS.')
