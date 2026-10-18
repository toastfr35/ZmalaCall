#!/bin/sh
# Camera/display-free checks. The Pi also exercises the ARM NEON preview path.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
task_build=$(mktemp -d "${TMPDIR:-/tmp}/zmala-video-tests-XXXXXXXX")
trap 'rm -rf "$task_build"' EXIT HUP INT TERM
if [ -n "${ZMALA_NATIVE_COVERAGE_DIR:-}" ]; then
    rmdir "$task_build"
    mkdir -p "$ZMALA_NATIVE_COVERAGE_DIR"
    task_build=$(mktemp -d "$ZMALA_NATIVE_COVERAGE_DIR/native-XXXXXXXX")
    trap ':' EXIT HUP INT TERM
    # Keep compiler counters outside the live application; no camera is opened.
    cc() { command cc "$@" --coverage -O0; }
fi
python3 - "$task_build/fixture.jpg" <<'PY'
import sys
from PIL import Image
Image.new('RGB', (640, 480), (40, 90, 160)).save(sys.argv[1])
PY
for task_name in test-auto-framing test-preview-display test-preview-adapter test-mjpeg-worker test-echo-rate test-camera-boundaries test-camera-filter; do
    cc -std=c11 -D_GNU_SOURCE -O2 -Wall -Wextra -Werror -pthread \
        "$task_root/tests/terminal/LLT/$task_name.c" -o "$task_build/$task_name" \
        -lmediastreamer2 -lortp -lbctoolbox -lm
    "$task_build/$task_name" "$task_build/fixture.jpg"
done

# T-LLT-045: missing-device size retention and coalesced codec recovery. This
# never opens a physical camera or starts the hardware encoder.
cc -std=c11 -D_GNU_SOURCE -O2 -Wall -Wextra -Werror -pthread \
    "$task_root/tests/terminal/LLT/test-video-recovery.c" \
    "$task_root/zmala_terminal/linux/media/video/codec.c" \
    "$task_root/zmala_terminal/linux/media/video/mjpeg-filter.c" \
    "$task_root/zmala_terminal/linux/media/video/mjpeg-stream.c" \
    -o "$task_build/test-video-recovery" \
    $(pkg-config --cflags --libs libavcodec libavutil) \
    -lmediastreamer2 -lortp -lbctoolbox -lm
"$task_build/test-video-recovery"
for task_name in test-encoder-buffers test-codec-boundaries; do
    cc -std=c11 -D_GNU_SOURCE -O2 -Wall -Wextra -Werror -pthread \
        "$task_root/tests/terminal/LLT/$task_name.c" \
        -o "$task_build/$task_name" \
        $(pkg-config --cflags --libs libavcodec libavutil) \
        -lmediastreamer2 -lortp -lbctoolbox -lm
    "$task_build/$task_name"
done
cc -std=c11 -D_GNU_SOURCE -O2 -Wall -Wextra -Werror -pthread \
    "$task_root/tests/terminal/LLT/test-video-filters.c" \
    "$task_root/zmala_terminal/linux/media/video/codec.c" \
    -o "$task_build/test-video-filters" \
    $(pkg-config --cflags --libs libavcodec libavutil) \
    -lmediastreamer2 -lortp -lbctoolbox -lm
"$task_build/test-video-filters"
if [ -n "${ZMALA_NATIVE_COVERAGE_DIR:-}" ]; then
    # Include untested authored C translation units in the denominator as well.
    for task_source in "$task_root"/zmala_terminal/linux/media/video/*.c "$task_root"/zmala_terminal/linux/media/audio/*.c; do
        cc -std=c11 -D_GNU_SOURCE -O0 -pthread -c "$task_source" \
            -o "$task_build/baseline-$(basename "$task_source" .c).o" \
            $(pkg-config --cflags libavcodec libavutil)
    done
    cd "$task_build"
    for task_notes in ./*.gcno; do gcov --json-format "$task_notes"; done
    python3 "$task_root/build_tools/native_coverage.py" "$task_root" "$task_build" "$ZMALA_NATIVE_COVERAGE_DIR"
    unset -f cc
fi
for task_name in test-mjpeg-worker test-preview-display; do
    cc -std=c11 -D_GNU_SOURCE -O1 -g -fsanitize=undefined -pthread \
        "$task_root/tests/terminal/LLT/$task_name.c" -o "$task_build/sanitized" \
        -lmediastreamer2 -lortp -lbctoolbox -lm
    UBSAN_OPTIONS=halt_on_error=1 "$task_build/sanitized" "$task_build/fixture.jpg"
done
