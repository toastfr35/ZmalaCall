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
components with their own notices. Before public binary distribution, assemble
the complete corresponding source and dependency notices for the shipped SDK,
including any codec components. Signing a release APK does not by itself complete
that source/notices package. Debug APKs are development artifacts.

ZXing Android Embedded 4.3.0 and ZXing core are Apache-2.0 dependencies. Their
source and notices are at https://github.com/journeyapps/zxing-android-embedded
and https://github.com/zxing/zxing. AndroidX libraries retain their Android Open
Source Project licenses. The Zmala logo is reused from the existing repository
asset; its Android vector uses the same geometry and colours.
