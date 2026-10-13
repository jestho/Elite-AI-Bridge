#!/usr/bin/env bash
# Linux counterpart of RUN_CURRENT_SOURCE.bat: sets up the private runtime on the first
# run, then starts Elite AI Bridge from this source tree. See LINUX.md.
exec "$(dirname "$(readlink -f "$0")")/Elite AI Bridge/start_linux.sh" "$@"
