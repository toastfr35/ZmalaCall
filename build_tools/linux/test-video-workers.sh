#!/bin/sh
# Camera/display-free checks. The Pi also exercises the ARM NEON preview path.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
task_build=$(mktemp -d "${TMPDIR:-/tmp}/zmala-video-tests-XXXXXXXX")
trap 'rm -rf "$task_build"' EXIT HUP INT TERM
python3 - "$task_build/fixture.jpg" <<'PY'
import sys
from PIL import Image
Image.new('RGB', (640, 480), (40, 90, 160)).save(sys.argv[1])
PY
for task_name in test-auto-framing test-preview-display test-mjpeg-worker; do
    cc -std=c11 -D_GNU_SOURCE -O2 -Wall -Wextra -Werror -pthread \
        "$task_root/build_tools/linux/$task_name.c" -o "$task_build/$task_name" \
        -lmediastreamer2 -lortp -lbctoolbox -lm
    "$task_build/$task_name" "$task_build/fixture.jpg"
done
for task_name in test-mjpeg-worker test-preview-display; do
    cc -std=c11 -D_GNU_SOURCE -O1 -g -fsanitize=undefined -pthread \
        "$task_root/build_tools/linux/$task_name.c" -o "$task_build/sanitized" \
        -lmediastreamer2 -lortp -lbctoolbox -lm
    UBSAN_OPTIONS=halt_on_error=1 "$task_build/sanitized" "$task_build/fixture.jpg"
done
