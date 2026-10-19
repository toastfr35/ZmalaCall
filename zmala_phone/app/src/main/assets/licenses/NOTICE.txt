# ZmalaPhone source and dependency notices

ZmalaPhone is an original focused Android interface using Linphone SDK 5.5.32.
Linphone Android 6.2.8 (commit dcaa165b77ed374b7beaedc8deae3e8a9b4fd30c) was inspected
as the reference for SDK ownership, camera/video surfaces, build versions and
call lifecycle. The full Linphone application UI has not been copied or forked.

Source references:
- https://gitlab.linphone.org/BC/public/linphone-android/-/tree/6.2.8
- https://gitlab.linphone.org/BC/public/linphone-sdk/-/tree/5.5.32
- https://wiki.linphone.org/xwiki/wiki/public/view/Lib/

The Gradle wrapper scripts/JAR and wrapper configuration originate from that
Linphone Android checkout. Preserve their embedded Apache License 2.0 notices.
The wrapper downloads Gradle 9.5.1; no separate system Gradle install is needed.

The TURN framing and write corrections compile against packet and socket class declarations
from the pinned mediastreamer2 header and oRTP/bctoolbox portability headers in
Linphone SDK 5.5.32. The build retains their original copyright and license
notices in its generated include directory. The checksum manifest and correction
source are in `build_tools/android/build-turn.py` and `app/src/main/cpp/`.

The new Android source in this directory is offered under AGPL-3.0-or-later,
matching the open-source SDK integration. See LICENSE.txt. This notice does not
relicense the rest of the Zmala repository. Linphone SDK is available under
AGPLv3 or a separate commercial agreement; it includes further third-party
components with their own notices. The release APK carries license texts under
`assets/licenses/`, including 278 notices from the pinned SDK and its external
components (including optional components that may not be enabled).
`build_tools/release/phone_notices.py` refreshes this inventory from the revisions
recorded in `SDK-SOURCES.json`. Debug APKs are development artifacts.

## Corresponding source access

The release description links the exact ZmalaCall commit containing the app,
native corrections and build/install scripts. The SDK's source, Android build
presets and dependency revisions are available without charge at:

- https://github.com/BelledonneCommunications/linphone-sdk/tree/5eaa11cfd2b052d9a9c71989faa0d55a8a8c57aa
- https://gitlab.linphone.org/BC/public/linphone-sdk/-/tree/5.5.32
- [SDK-SOURCES.json](SDK-SOURCES.json): exact source repository and commit for
  every external submodule, including codec libraries.

To retrieve the SDK and all its dependencies using their original public URLs:

```sh
git clone --branch 5.5.32 --recurse-submodules https://gitlab.linphone.org/BC/public/linphone-sdk.git
```

The SDK GitHub ZIP by itself does not contain external submodules. Use the
recursive clone or fetch each repository at the commit listed in the manifest.
The source is provided through these versioned repositories rather than an
additional release attachment. Keep this source access and the dependency notices
available when redistributing the APK; update them when upgrading the SDK.

ZXing Android Embedded 4.3.0 and ZXing core 3.4.1 are Apache-2.0 dependencies. Their
source and notices are at https://github.com/journeyapps/zxing-android-embedded/tree/v4.3.0
and https://github.com/zxing/zxing/tree/zxing-3.4.1. AndroidX libraries retain their Android Open
Source Project licenses (https://android.googlesource.com/platform/frameworks/support/).
Firebase Messaging and its open-source dependencies retain their Apache-2.0
notices (https://github.com/firebase/firebase-android-sdk); Google Play services
libraries are distributed under their Android SDK terms. The exact dependency
versions are resolved by the pinned Gradle build and Firebase BOM.
The Zmala logo is reused from the existing repository
asset; its Android vector uses the same geometry and colours.
