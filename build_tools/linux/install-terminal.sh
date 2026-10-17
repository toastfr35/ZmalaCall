#!/bin/sh
# Debian / Raspberry Pi OS packages; use the system Python, not a pip venv.
set -eu
sudo apt-get update
task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
xargs sudo apt-get install -y --no-install-recommends < "$task_dir/dependencies.txt"
if [ "${1:-}" = '--testing' ]; then
    sudo apt-get install -y --no-install-recommends xvfb xauth x11-utils
fi
sh "$task_dir/build-media.sh"
printf '\nInstalled ZmalaCall terminal dependencies. Run it inside an X11/XWayland desktop session.\n'
