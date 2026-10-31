# In-call photo sharing implementation plan

Feature request: https://github.com/toastfr35/ZmalaCall/issues/67

Status: implemented on the feature branch. Local checks and emulator call tests pass;
physical phone/terminal qualification is in progress. This is a
work checklist, not a substitute for normative requirements under requirements/.

## Intended experience

An app user selects a photo during a connected call to a terminal. The same
photo fills the terminal display in place of both video views and appears on the
phone. Images keep their proportions. Voice and call controls remain available.
The sender stops sharing to return to video. Ending the call clears the photo.
The scope includes App-to-Terminal and App-to-App calls, with one shared photo at a time.
Either app may start a share when none is active; only its sender may renew or stop it.
Both phones display the photo while voice continues. Receiver polling must survive
rotation, clear on stop/end/expiry, and never renew another phone’s share.

## Implementation order

1. Add stable PROD → component HLR → LLR links for server, Android and terminal,
   allocating IDs through build_tools/requirements.py --next-id. Add reciprocal
   LLT/HLT plans and implementation trace comments with each completed layer.
2. Server: add an ephemeral call-photo service alongside the existing authenticated
   device routes. Authorize against SipServer.dialogs, connected state and exact
   enrolled App/Terminal participants. Keep photos outside portrait/public routes.
   Bound file and decoded-pixel sizes, normalize orientation and strip metadata.
   Recheck authorization after decode/upload; clear on stop, call end or expiry.
   Use revision identifiers so late uploads cannot resurrect a stopped share.
3. Android: use the system image picker without broad library permission. Bind
   upload/share state to CallSession.callId(), not Activity lifetime. Add choose/
   stop-sharing controls and an aspect-preserving photo layer in CallScreen.
   Keep audio and hang-up usable, handle rotation and picker cancellation, and
   reject late picker/upload results after the call changes. Localize EN/FR.
4. Terminal: retrieve authenticated current-call sharing state off the Tk thread.
   Add an aspect-preserving image layer over remote and self-view, leaving native
   media surfaces alive so stopping sharing restores video promptly. Fence work
   by call identity and photo revision; discard data on call end or stop.
5. Tests: authorization and wrong-call isolation; image bounds and invalid data;
   concurrent stop/end versus upload; photo replacement; network failure; rotation
   and background activity lifetimes; audio continuity and video restoration.
   Run local server tests, Linux virtual-display terminal tests and Android tests.
6. Update technical and editable user guides, regenerate affected PDFs, and raise
   the Android release version above main. Run lint and requirements validation.
   Hardware qualification is a separate recorded step when devices are available.

## Existing integration points

- zmala_server/http/device-routes.js: enrolled bearer-token identity.
- zmala_server/sip-dialogs.js and sip-server.js: connected peer identities and teardown.
- zmala_phone/.../CallSession.java: retained call ownership and SIP call ID.
- zmala_phone/.../CallScreen.java: media surfaces and in-call actions.
- zmala_terminal/common/engine.py: native call log ID on the core owner thread.
- zmala_terminal/common/configuration.py: authenticated requests with no redirects.

Do not reuse portrait storage, publish photos, change account pictures, or
claim a hardware call test passed from fixture-only evidence.

## Validation record

- Server suite: 234 passed, 5 skipped; new private-call route and normalization tests pass.
- Terminal LLTs: 562 passed, 11 skipped. Four focused photo/layout tests pass under Linux Xvfb.
- Android JVM tests, lint and signed release build pass. Both new device tests pass on the
  disposable Android emulator, including a native SIP call and visible photo layer.
- Requirements report rebuild passes with reciprocal LLT/HLT plans and implementation traces.
- Phone/terminal editable guides updated; release PDFs regenerated and visually inspected.
  Native Word rendering was unavailable locally because LibreOffice is not installed.
- Test version 0.3.38 (47) installed on the connected phone without clearing enrollment;
  targeted server and terminal source updates deployed with rollback backups.
- Physical system-picker selection, two-screen display and audible speech still need a
  real call. The phone remained locked; fixture results are not hardware qualification.
  Terminal automatic-answer settings were restored while waiting for the user.

## Scope extension: App-to-App (requested after initial phone test)

App-to-App extension implemented and tested:

1. Completed: track the sender account on the server and permit App/App dialogs. Atomically
   claim an idle share; reject competing uploads and non-sender renewal/deletion.
2. Completed: add a session-owned Android receiver that polls status and fetches bounded
   authenticated image bytes. Keep sender and receiver state distinct, including
   lease deadlines and late-result fencing. A receiving phone must not show Stop
   sharing as though it owns the photo.
3. Completed: enable selection for either contact type, update requirements and guides, and
   exercise both directions and simultaneous attempts in Android/server fixtures.
4. Physical qualification remains partial. Initial OnePlus test successfully opened
   the system picker, selected the synthetic image, displayed it and stopped sharing
   without ending the call. The terminal screenshot attempt failed X authorization;
   terminal display and physical speech remain unqualified. Test call ended and
   terminal automatic-answer settings were restored.


App-to-App validation: eight focused server tests pass, including authenticated image
retrieval in both directions, competing claims and non-sender mutation rejection.
Android image and native-call integration tests pass on the disposable emulator,
including receiver stop and failure/lease expiry without ending the native call.
Android lint and signed build pass. Updated server and signed OnePlus candidate
are installed; a two-physical-phone sharing test has not been performed.
