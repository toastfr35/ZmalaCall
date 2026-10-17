#!/bin/sh
# Optional local detector. No downloads occur when a call starts.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
media="$task_root/zmala_terminal/media"
python3 -m venv --system-site-packages "$media/framing-runtime"
"$media/framing-runtime/bin/python" -m pip install --only-binary=:all: 'ai-edge-litert==2.3.0'
python3 "$task_root/build_tools/linux/download-framing-model.py" "$media/models/person.tflite"
printf 'Automatic framing installed. Enable it in the server terminal settings.\n'
