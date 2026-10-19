# ZmalaPhone implementation guide

ZmalaPhone is the Android companion in `zmala_phone/`, package `org.zmala.phone`.

Version 0.3.6 supports encrypted calls through the server's TLS/TURN relay from

separate NAT networks, alongside LAN mode and Firebase incoming-call alerts while

the activity is closed. Remote mode needs a publicly reachable, configured secure

deployment and HTTPS enrollment. Leaving an active call ends media and registration;

callback-message presentation is not implemented.

Normative scope and verification plans live in `requirements/android/`; this

file describes the implementation and its current limitations.

## Account setup

The administrator creates an **App** account, adds it to a calling group, and

downloads the server QR PDF from its connection dialog. They give the phone user

the QR by email or on paper. The phone user does not need server admin access.

Install the supplied signed release APK, tap **Scan setup QR**, allow camera and microphone access (also local network

access on Android 17), scan the code and confirm the displayed server address.

An HTTP enrollment explicitly warns that LAN setup and calls are unencrypted.

For a QR received by email, display it on another screen to scan it with the phone.

LAN mode needs a mutually reachable trusted network. Secure relay mode supports

separate networks through the administrator's public Zmala server.

Allow notifications when prompted to receive calls while using another app or

when the phone is asleep. The phone and Pi need internet access for Firebase.

If notifications are denied, enable them in Android Settings > Apps > ZmalaPhone >

Notifications, then reopen ZmalaPhone. Android Force stop blocks delivery until

the app is opened again; swiping it from Recents is not the same operation.

A green App contact can be reachable through push even when its activity is closed.

An account has exactly one type, App or Terminal. The two types have separate

device identities and enrollment tokens. A Terminal QR is rejected by the app;

an app token cannot read Pi configuration or use terminal management APIs.

Switching types rotates the device identity, bearer token and SIP password.

Print a fresh QR after conversion. This does not turn one account into two devices.

One account still supports one active SIP registration and call.

The contact view uses server group permissions, account names and portraits.

Compact horizontal rows place a rounded 72 dp portrait beside the name, with

8 dp between rows. Online names have green backgrounds and start a call when

tapped while registered; offline names are gray and disabled. Screen readers

announce availability. There is no separate availability label or call button.

The contact screen omits the phone account name and routine ready-to-call status;

connection errors remain visible.

Long names may wrap and increase row height rather than truncate.

Short lists are vertically centered between the header and preview notice;

longer lists start at the top and scroll. The contact ScrollView fills its viewport

and its row container centers its children when extra height is available.

During outgoing and connected calls, video replaces the logo banner and contact

name. The local camera preview sits at bottom right. Tap the video to reveal one

row of four round icons: microphone, audio output, switch camera and hangup.

The controls start hidden and disappear after five seconds without interaction;

using a control restarts that timer. The preview sits above the visible row and

returns to the corner when it hides. The call view adapts to portrait and landscape

without replacing the call or video surfaces, and sends display rotation to the

native camera engine. Physical remote-video orientation still needs qualification.

A pulsing phone indicator shows Calling or Ringing until the call connects.

After answer, a spinner and “Connecting video…” remain until the current call's

first decoded remote frame. The progress container spans the available width with
24 dp side margins so its label is not clipped to the spinner's width. `VideoStartup` re-arms the SDK's one-shot frame

notification during initial stream restarts and ignores stale call callbacks.

It logs only the monotonic answer-to-frame duration under `ZmalaMedia`; no account,

address or media content is included. This measures decoder delivery, not display scanout.

The engine explicitly enters foreground after start: it is created asynchronously

after the activity has resumed, so the SDK lifecycle observer otherwise misses

that transition and eventually drops to its 500 ms background iteration timer.

The foreground timer runs at 20 ms; activity stop still releases the core.

Incoming calls retain the caller name and answer/decline actions before answering.

Call and answer controls are green; decline and hangup are red. The dark palette

comes from `zmala_terminal/common/theme.py`; the Android vector reproduces

`zmala_server/assets/zmala-icon.svg`. To remove enrollment, use Android Settings > Apps > ZmalaPhone > Storage >

Clear storage (called Clear app data on some phones), then scan an App QR again.

This stops the app and removes its local data; the server account is unchanged.

There is no reset action within the app. There is no manual SIP editor or public Linphone account assistant.

## Sources and ownership

This is a small Zmala UI around the Linphone SDK, not a wholesale copy of Linphone's

messaging/account UI. Linphone Android 6.2.8, commit

`dcaa165b77ed374b7beaedc8deae3e8a9b4fd30c`, was the source reference; its Gradle

wrapper is retained. The Android SDK dependency is pinned to 5.5.32.

See `zmala_phone/NOTICE.md` for source and license provenance.

`Enrollment` validates QR and configuration identity and verifies the incoming

`X-Family-Auth` HMAC over `callId:callerUsername`. `ServerApi` sends the bearer token

only to paths on the enrolled origin, refuses redirects, applies six-second

connection/read timeouts and bounds configuration and photo response sizes.

`MainActivity` owns asynchronous configuration refresh, generation-based stale

response rejection, screen state and private enrollment storage. Only the QR

payload is retained in `getNoBackupFilesDir()`; fetched SIP passwords are in memory.

The app does not save them into Linphone's configuration or a call-history database.

`CallEngine` owns the SDK on Android's main thread. It uses the supplied proxy,

Digest credentials, one call, audio/video codecs, no RTP bundle and no ICE in

LAN mode. `SecureCalls` validates encrypted relay policy and configures SIP TLS,

TURN TLS, forced ICE relay and mandatory SRTP in secure mode. Certificates and

names are verified using Android's trusted roots; the server cannot inject a CA.

The roots are exported atomically into the app's private no-backup directory and

passed as a CA file, because native TURN TLS needs a file rather than SIP's PEM-data API.

`TurnTransport` loads the native framing correction before the SDK. Its global

ELF symbol replaces the pinned SDK's fragmented TURN packet reader; the live

hardware test verifies that this reader actually handles relay traffic. The

same library corrects TLS writes that the SDK otherwise drops on socket

backpressure. The shared writer in `zmala_terminal/common/native/turn-write.h`

retains buffers across retries and short writes, waits in 100 ms polls, and

fails after three seconds. A failed write shuts down the connection, preventing

subsequent frames from following an incomplete TLS payload. Live tests check

the writer invocation counter as well as the reader counter.

Checksum-pinned SDK headers preserve the native class ABI. Changing the SDK

requires requalifying the correction; mismatched source or binary hashes stop the build.

Both TLS endpoints accept explicit ports so one public IP can host all services.

The native core enables AVPF feedback and NACK retransmission to recover video

packets and request fresh decoder initialization after ICE path changes.

Incoming calls must match both the directory and the server proof.

It binds the remote TextureView and the SDK CaptureTextureView for local video,

which receives actual camera dimensions and sensor/display transforms to preserve

proportions and orientation. `CallScreen` chooses the preview slot dimensions from

the incoming measure bounds before measuring children, so an orientation change

does not leave the video in the previous layout's dimensions. It exposes answer, hangup, mute,

speaker and camera controls. Camera switching uses `Call.update(null)` after selecting

the other camera, keeping the operation local rather than initiating a new SDP/ICE

negotiation that can defer or disrupt successive switches. `CallScreen` owns the overlay layout, original line

icons, five-second idle timer and outgoing progress animation; it cancels timers

and animation on teardown. The ringing circle and phone glyph animate their drawn

size and opacity inside a fixed 108 dp surface with at least 12 dp of clear margin;

the view itself is not scaled or faded, avoiding clipping by composited view bounds.

Rotation is handled in the existing activity through

configuration and display callbacks. On stop it terminates calls and unregisters.

Secure configuration requires an HTTPS setup QR and complete, unexpired TURN

credentials. There is no plaintext retry after a TLS or relay failure. Hourly

credential changes remain pending while in a call and rebuild the core at the

next idle refresh. Expired applied credentials cannot start another call.

Server configuration polls occur every ten seconds while open.

## Build and verification

Use native Windows Android Studio and SDK for device access and emulator testing;

WSL is not needed for app development. The repository wrapper pins Gradle 9.5.1

and AGP 9.2.1. Use JDK 21 or newer compatible with these tools. Compile/target API

is 37; minimum API is 28. APKs include arm64-v8a and x86_64. The native correction

uses NDK 29.0.14206865 and Python 3. The Gradle build uses the repository virtual

environment when present, otherwise `python3`; `PYTHON` can select another interpreter.

`build_tools/android/build-turn.py` downloads checksum-pinned SDK headers and builds

the correction for both ABIs, using the AAR's own C++ runtime. Its JNI regression

helper is packaged only in the test APK.

On the prepared Windows PC:

```powershell

. C:/Users/antoi/Android/toolchain-setup/android-env.ps1

make phone test-android

$env:ANDROID_SERIAL = 'emulator-5580'

make test-android-device

# Clears only the explicitly selected disposable emulator, never a physical phone:

.venv/Scripts/python.exe tests/android/LLT/clear_storage.py

```

The APK is `zmala_phone/app/build/outputs/apk/debug/app-debug.apk`. Debug signing

is for development. Do not use it as a public release. The Android CI job builds

and runs JVM tests/lint; device tests run explicitly against the selected device.

Keep the selected phone unlocked and awake for UI scenarios. No connected device

means those tests were not run.

Tests remain in the repository's top-level tree: JVM LLTs under

`tests/android/LLT/unit`, device LLTs under `tests/android/LLT/device`, and HLTs

under `tests/android/HLT`. Shared disposable HTTP and SIP fixtures live under

`tests/support/android`. They test QR-result handling, identity boundaries,

redirect rejection, contact UI and Android app-data clearing and native Digest registration, outgoing

video SDP, signed incoming admission, answer and cleanup. They do not claim

optical QR scanning, media quality or full physical Pi interoperability.

The existing `coverage-llt` percentage measures Pi server/terminal execution;

Android test results are separate and do not contribute to that percentage.

Before accepting a release, scan a real printed App QR on a phone, register with

the Pi, call both directions and check moving video, intelligible audio, mute,

earpiece/speaker and front/back camera switching. Also exercise decline, remote

hangup, unavailable contact, Wi-Fi loss, account conversion, app backgrounding,

rotation and large-font layouts. Record phone model/Android version, Pi build,

network and observed media results. A signalling fixture is not a passed media test.

## Firebase incoming calls

The optional local `app/google-services.json` is compiled into Firebase resource

values; CI fixture builds can omit it. Firebase Messaging uses BoM 35.0.2 with no

Analytics dependency. The Firebase Messaging integration can use the no-cost Spark plan; this path

needs no paid Functions or database. `PushService` validates an HMAC using the

private enrollment token before showing a native CallStyle notification. The

payload contains caller ID, call ID, event, expiry, device ID and proof; the caller

name is taken from a local cache, not sent through Google. SIP credentials and

media do not pass through Firebase.

`PushAlerts` requests notification permission, registers the token against the

App bearer and renews it at most hourly while open. Disabling notifications removes

the destination on the next app open. New tokens replace old ones; reinstalling or

clearing storage requires enrollment again. Server tokens expire after 30 days

without renewal: reopen the app to renew. Invalid FCM destinations are removed.

An enabled footer means token registration succeeded, not a delivery guarantee.

The server waits for fresh SIP registration for up to 60 seconds, including when

an older registration still exists. The signed notification has an expiry and

Answer/Decline actions (Android may label video answer as **Video**). Answer opens

the activity, reloads the permitted directory and registers; only the matching

unexpired, independently authenticated SIP INVITE can be auto-answered.
Notification answering is queued onto the next main-loop turn, so native
incoming-state handling finishes before acceptance. The queued
action rechecks call identity, incoming state, activity visibility and expiry.
Decline sends a bearer-authenticated cancellation. Caller cancellation sends a signed

cancel message. Expiry dismisses the alert even if cancellation is delayed; a

short local tombstone rejects reordered ring messages after cancellation.

Android can show the incoming screen over the lock screen when full-screen-call

permission is available; otherwise it presents the call notification. No permanent

foreground service, background microphone or camera is used. Notification/channel

permissions, Android Force stop, OEM battery restrictions, connectivity and Google

Play services affect delivery. Qualify these on the actual target phone; emulator

callback tests do not establish FCM delivery or Doze reliability. Keep the activity

open during an answered video call. Sender setup is in [server.md](server.md).

## Signed release builds

Release packaging is separate from the runtime requirements. Set up Java and the
Android SDK as above, then run `python build_tools/android/release.py`. The helper
defaults to `~/.zmala/signing/android-release.json`; `--signing` selects another
private file outside the checkout. Its fields are `storeFile`, `storePassword`,
`keyAlias`, `keyPassword` and the pinned public `certificateSha256` fingerprint.
The keystore must also be outside the checkout. Restrict both files to the release
operator and back them up securely off this PC. Losing this identity prevents
updates to APKs already distributed with it. Never create a replacement key merely
because a build machine is missing the original.

The helper runs portable JVM tests plus release lint and assembly, verifies the APK signature
against the pinned certificate, checks 16 KiB ZIP alignment and rejects debuggable,
test-only, wrong-package or backup-enabled APKs. Output is in
`build_tools/dist/ZmalaPhone-<version>/ZmalaPhone.apk`, with local SHA-256 checksum,
public signature details and license notices alongside it. The release collector
uploads only the APK and six PDF guides/two Pi installers described in
[general.md](general.md#release-download-layout). Gradle uses
`ZMALA_RELEASE_SIGNING` for this private JSON and fails release preparation when
signing or Firebase client configuration is absent. Debug builds remain available
without either for disposable tests. The normal Verify workflow receives no signing
secrets. The manual Publish release workflow uses encrypted repository Actions
secrets only in its Android job; see [release automation](general.md#github-actions-publication).

The first signed release is 0.3.6, version code 15, Android 9/API 28 or newer,
arm64-v8a and x86_64. It uses the qualified native libraries without adding code
shrinking. Subsequent releases must increase the version code and retain the same
signing identity. Release and development APKs have different certificates:
Android cannot install one over the other. Obtain a fresh enrollment QR before
uninstalling an existing development copy; uninstalling removes its setup. Do not
remove users' working development installations automatically.

For website or GitHub distribution, users download the APK, authorize installation
from that browser/file manager, install and scan their private setup QR. Subsequent
signed release APKs install as updates and preserve setup. The download is public;
account QR codes, server keys, signing files and diagnostic captures are private.
The source repository does not contain a deployment's `google-services.json`;
builders supply their own Firebase Android configuration. Firebase client project
identifiers/API configuration are necessarily embedded in the configured APK and
are not server sender credentials. See `zmala_phone/NOTICE.md` for corresponding
source access and packaged dependency notices. The APK includes the AGPL and Apache
licenses and the pinned SDK/component notice inventory under assets/licenses/.

## Qualification record

Development versions were exercised on a OnePlus KB2003/Android 14 and a POCO F1/
Android 10, including QR enrollment, permissions, foreground calls, camera switching,
rotation, native incoming-call notifications and secure relayed media. MIUI required
on-device APK installation. This is a bounded device sample, not universal OEM
compatibility. Private device identities, enrollments and captures are not published.

The 0.3.6 changes address deferred notification answering and cooperate with the Pi's
first-picture keyframe retries. A C20 USB timeout was recovered operationally by
cycling its power; its underlying trigger remains undetermined. Four Pi-to-phone
calls passed with remote video on both screens: two process-absent push starts and
two foreground starts. Six further calls alternated phone-to-Pi and Pi-to-phone
three times without restarts, all displaying remote video at both ends. Native
samples showed relay ICE, increasing received packets and nonzero phone decode
rates. Rates varied approximately 4–34 fps in the alternating run; neither uniform
smoothness, exact startup latency nor audible speech is inferred from those samples.
Temporary answering controllers were stopped and diagnostic logging disabled.

Nine portable Android tests, lint, two emulator notification checks, the focused Pi
native filter regression and requirement validation passed for the 0.3.6 changes.
The new native first-picture regression also failed against the old implementation.
Hardware observations do not mark unexecuted HLT plans passed. The signed 0.3.6
release also passed APK signature, alignment and manifest checks. Seven emulator
checks against the non-debuggable release covered scanner launch, enrollment/call
flow, native call-engine ownership/camera switching and notifications. The test APK
was signed privately with the same release identity for instrumentation; it is not
a distribution artifact. Release lint reported zero errors and six existing
warnings. Packaging checks rejected missing signing and missing Firebase inputs.
Physical call qualification used the same 0.3.6 sources in the development variant;
the release certificate was not installed over existing phones' debug enrollment.
