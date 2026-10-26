# ZmalaPhone UI improvement plan

Created 26 October 2026. Work proceeds in the numbered order below. This is a
delivery checklist; normative product behavior remains in `requirements/`.

Preserve the terminal palette and logo, compact portrait contact cards, portrait-only
contacts, contact-only version label, four call controls, five-second default control
visibility, separate microphone and listening controls, and current enrollment data.

## Work sequence

1. [x] **Simple contact navigation and clear notices.** User refinement: each contact
   is one tappable card, opening a dedicated page with Call, Request/Cancel callback,
   missed-call information and Clear missed calls. Offline contacts remain openable;
   only Call is disabled. Include readable request direction, simultaneous notices,
   long names, Back/Contacts navigation and current server permissions.
2. [x] **QR images.** Add a system image-picker action beside scanning, decode a QR
   locally with bounded image work, and use the same enrollment validation/confirmation.
   Explain missing/invalid codes without requiring administrator access or another screen.
3. [x] **Personal incoming calls.** Show caller portrait, name and incoming-video-call
   wording, with distinct Answer and Decline actions and a safe portrait fallback.
4. [x] **Discoverable call controls.** Add a brief first-call tap/swipe hint, short
   labels when controls appear, and compact persistent microphone/listening mute indicators.
   Retain uncluttered video, preview positioning and four controls in one row.
5. [x] **Connection feedback.** Bound the initial video-connecting presentation, show
   calm delayed-video feedback afterward, and distinguish transient server reconnection
   from errors that need user action. Never end a usable call because video is late.
6. [x] **Actionable incoming-alert status.** Distinguish disabled notifications from
   unavailable push/server support; offer the relevant Android Settings action and retain
   a quiet contact-screen footer for normal status and installed version.
7. [x] **Quiet updates with progress.** Replace unsolicited update dialogs with an
   available-update indicator. Show download progress, verification and installation
   stages after selection; preserve optional idle automatic updates and call exclusion.
8. [x] **Accessibility and language.** Supply English/French UI strings chosen from
   the phone language, support long names and enlarged fonts, accessible status labels,
   focus-aware control visibility and Android accessibility timeout preferences.
9. [x] **Calls while switching apps.** Move active-call/core/audio ownership out of
   the activity into a foreground call service, supply an ongoing return/end-call
   notification and reattach video safely on return. Stop camera capture while hidden;
   preserve audio where Android permits it. Keep idle push reception lightweight,
   explicit hangup effective and background/force-stop limitations clear. Cover Back,
   Home, screen locking, activity recreation and service cleanup separately.

## Completion checks for each step

- [x] Identify affected Android PROD/HLR/LLR items and owning `@llr` trace comments.
- [x] Update technical documentation and affected guide authoring sources together.
- [x] Add meaningful direct LLT and HLT plans/assertions under `tests/android/`.
- [x] Run the relevant JVM/native-display checks and `make requirements`.
- [x] Record actual evidence below; compilation is not a passed device run.

## Final integration

- [x] Regenerate affected Word/PDF guides through their build tools and inspect output.
- [x] Run Android JVM tests, lint, debug APK and instrumentation APK builds.
- [x] Run repository lint, requirements validation and affected offline regressions.
- [x] Use the repository issue/feature-branch/pull-request workflow and increase the app
  version above current `main` before a pull request. Keep credentials/private evidence out.
- [x] Review the complete diff and record remaining physical qualification explicitly.

## Evidence and remaining qualification

The terminal is off and no phone is connected at the start of this work. Do not
wake or reconfigure either to obtain evidence. Use offline tests and an available
emulator where practical. Real phone camera/audio, locked-screen/Doze behavior,
vendor battery policies and cross-network calls need separately recorded device runs.

Progress and test results will be added here as each step completes.

- Tracking issue: https://github.com/toastfr35/ZmalaCall/issues/19.
- Step 1: visible notice wording and simultaneous-state JVM assertions implemented;
  `NoticeBookTest` passed on Windows. Device assertions are queued for emulator integration.
- Step 2: debug/instrumentation APK builds passed. `QrImageTest` passed on the disposable
  Android 37 emulator (exact QR decode, invalid/non-QR/oversized input and stream closure).
- Contact navigation refinement: `InterfaceTest` passed both emulator cases, including
  offline actions, Request/Cancel HTTP lifecycle, missed clearing and Call from a detail page.
- Step 3: enlarged-text incoming screen test passed on the emulator (caller portrait,
  scrollable layout and independent Answer/Decline actions).
- Step 4: six `CallScreenTest` emulator cases passed, including portrait/landscape button
  geometry, preview placement and timer behavior. Additional hint/mute assertions are included
  in the next focused run.
- Step 5: JVM delayed-video/recovery tests and all debug builds passed. Three emulator
  cases passed: first-call hint/mute/delayed message, image confirmation cancellation,
  and a real native call surviving HTTP 503 but stopping after authenticated HTTP 403.
- Step 6: alert-policy JVM checks and builds passed. The emulator notification-status
  flow passed and verified that Enable notifications opens Android's app settings action.
- Step 7: JVM/build checks passed. Emulator update UI test confirmed that discovery
  changes the footer without a dialog and a chosen update renders determinate download
  progress and indeterminate verification. This is UI evidence, not a self-update run.
- Step 8: JVM tests, lint and APK builds passed. Four emulator cases passed: French
  resources/plurals, 200% font layouts/focused controls, and both contact-navigation cases.
  Predictive Back uses Android's callback on newer phones, with a legacy fallback.
- Step 9: JVM lifecycle/identity checks, lint and APK builds passed. `CallContinuityTest`
  passed on the disposable Android 37 emulator: same call/core through Home, activity
  recreation and screen-off; camera pause/restore; stale End rejection; notification hangup
  with registration/notification/audio cleanup. Physical media and vendor/Doze checks remain open.

Final local integration on 26 October 2026:

- Android JVM suite: 27 tests passed, no skipped cases. Debug lint completed with
  zero errors and 14 warnings; debug and instrumentation APK builds passed.
- Disposable Android 37 emulator: the 25-case main instrumentation run passed.
  A separate eight-case follow-up passed with notifications deliberately denied,
  exercising the Settings action, missing-permission service cleanup, real French
  app-locale switching and repeat contact-action navigation. Earlier failed test
  assumptions were corrected before these runs; no skipped permission case is
  counted as verification.
- Repository lint, requirements and ad-hoc tooling checks passed. The requirements
  report maps 240 source files, 248 code-anchored LLRs and 219 test plans, with no
  unmapped HLR or LLR. Tooling checks are separate from product qualification.
- Regenerated four affected Word sources and all six release PDFs. Rendered and
  inspected affected Word and PDF pages; no clipping or overlap was found. Inspected
  English/French contact list and person-page screenshots with synthetic contacts.
- Version is 0.3.17 (code 26), above main's 0.3.16. No phone or terminal deployment
  was performed. Emulator media-state checks do not establish real camera/audio
  quality, physical locked-screen delivery or vendor battery-policy behavior.

Additional hardware session after the user connected the OnePlus and powered term2:

- Installed the signed 0.3.17 candidate over 0.3.16 on the OnePlus 8T (Android 14),
  preserving its enrollment and directory. Inspected the real person page and offline
  Call-disabled behavior without sending test callback notifications to family members.
- The first two calls exposed a terminal credential-renewal fault: configuration caching
  contained a fresh relay policy but the poll controller ignored it at an unchanged
  revision. TURN rejected the expired native credential. Added a direct LLT and a real
  Tk controller HLT for same-revision renewal and deferred application during a call.
  Ten focused LLTs, four display HLTs, repository lint and requirements passed; the full
  terminal LLT run passed (496 cases, 11 platform-specific skips).
- Installed only the small renewal-dispatch fix on idle term2, with a private backup of
  its previous file. The next phone-to-terminal call displayed video on both devices;
  the phone reported its first decoded frame 2.611 seconds after answer. Home paused
  camera sending while the foreground call service remained active. The ongoing
  notification returned to the same call and both video views resumed. Hangup removed
  the foreground call service. Physical sound quality and vendor/Doze behavior remain
  separate qualification work.
- The reverse terminal-to-phone call reached the phone from Home through Firebase
  notification, displayed the caller portrait and separate answer/decline actions,
  and showed decoded video on both devices after answer. The phone's first frame was
  recorded at 2.285 seconds. This is a real handset smoke check on Wi-Fi, not a
  cellular, deep-Doze or acoustic qualification.
