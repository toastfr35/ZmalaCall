#!/bin/sh
# Internal maintenance tool: follow the active release after upgrades/rollback.
set -eu
exec /usr/bin/python3 /opt/zmalacall/current/build_tools/linux/tv-plugin-self-test.py "$@"
