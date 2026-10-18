#!/bin/sh
# Camera/display-free checks. The Pi also exercises the ARM NEON preview path.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
task_build=$(mktemp -d "${TMPDIR:-/tmp}/zmala-video-tests-XXXXXXXX")
trap 'rm -rf "$task_build"' EXIT HUP INT TERM
python3 - "$task_build/fixture.jpg" <<'PY'
import sys
from PIL import Image
Image.new('RGB', (640, 480), (40, 90, 160)).save(sys.argv[1])
PY
for task_name in test-auto-framing test-preview-display test-mjpeg-worker; do
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
cc -std=c11 -D_GNU_SOURCE -O2 -Wall -Wextra -Werror -pthread \
    "$task_root/tests/terminal/LLT/test-encoder-buffers.c" \
    -o "$task_build/test-encoder-buffers" \
    $(pkg-config --cflags --libs libavcodec libavutil) \
    -lmediastreamer2 -lortp -lbctoolbox -lm
"$task_build/test-encoder-buffers"
for task_name in test-mjpeg-worker test-preview-display; do
    cc -std=c11 -D_GNU_SOURCE -O1 -g -fsanitize=undefined -pthread \
        "$task_root/tests/terminal/LLT/$task_name.c" -o "$task_build/sanitized" \
        -lmediastreamer2 -lortp -lbctoolbox -lm
    UBSAN_OPTIONS=halt_on_error=1 "$task_build/sanitized" "$task_build/fixture.jpg"
done
