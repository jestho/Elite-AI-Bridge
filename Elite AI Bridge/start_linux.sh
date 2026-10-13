#!/usr/bin/env bash
# Elite AI Bridge 2.0.0 - Linux launcher (Elite Dangerous running under Steam Proton).
#
# Does what START_HERE.bat + Installer_Runtime_Setup.ps1 do on Windows:
#   1. finds Python 3.12+ and checks the system packages the runtime needs,
#   2. builds the Bridge's private runtime (a venv) with the exact pinned packages,
#   3. downloads the Supertonic voice model on the first run,
#   4. starts the Bridge.
#
# Usage:  start_linux.sh            set up if needed, then start
#         start_linux.sh --setup    rebuild the private runtime, then start
#         start_linux.sh --check    only check Python and system packages
#         start_linux.sh --paths    show where the Bridge looks for Elite's files
#         start_linux.sh --input    check cockpit key sending, hotkeys (uinput, keyboards, X11 tools)
#
# Everything the Bridge writes goes to $XDG_DATA_HOME/EliteAIBridge (usually
# ~/.local/share/EliteAIBridge). See LINUX.md in the top folder for the details and
# for the environment variables that override the detected paths.
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"
APP_ROOT="$PWD"
DATA_DIR="${ELITE_AI_BRIDGE_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/EliteAIBridge}"
RUNTIME_DIR="$DATA_DIR/runtime"
VENV="$RUNTIME_DIR/.venv"
VENV_PY="$VENV/bin/python"
READY_MARKER="$RUNTIME_DIR/.ready"
LOG_DIR="$DATA_DIR/logs"
SETUP_LOG="$LOG_DIR/runtime_setup.log"

MODE="run"
case "${1:-}" in
    --setup) MODE="setup"; shift ;;
    --check) MODE="check"; shift ;;
    --paths) MODE="paths"; shift ;;
    --input) MODE="input"; shift ;;
    -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
esac

mkdir -p "$LOG_DIR"
log() { printf '%s\n' "$*"; printf '[%s] %s\n' "$(date -Is)" "$*" >> "$SETUP_LOG"; }
fail() { log "SETUP FAILED: $*"; log "Log: $SETUP_LOG"; exit 1; }

echo "============================================"
echo "        ELITE AI BRIDGE 2.0.0 (Linux)"
echo "============================================"
echo

# --- 1. Python and system packages -------------------------------------------------
find_python() {
    local candidate
    for candidate in python3.13 python3.12 python3; do
        if command -v "$candidate" >/dev/null 2>&1 &&
           "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
            command -v "$candidate"
            return 0
        fi
    done
    return 1
}

SYSTEM_PY="$(find_python || true)"
[ -n "$SYSTEM_PY" ] || fail "Python 3.12 or newer was not found. Install it with your package manager (python3, python3-venv)."
log "Using $SYSTEM_PY ($("$SYSTEM_PY" --version 2>&1))"

MISSING=()
# tkinter is part of Python's standard library but most distributions package it separately.
"$SYSTEM_PY" -c 'import tkinter' 2>/dev/null || MISSING+=("tkinter: Debian/Ubuntu 'python3-tk', Fedora 'python3-tkinter', Arch 'tk'")
"$SYSTEM_PY" -c 'import venv, ensurepip' 2>/dev/null || MISSING+=("venv: Debian/Ubuntu 'python3-venv'")
# sounddevice needs the PortAudio shared library (the Linux wheel does not bundle it).
"$SYSTEM_PY" -c 'import ctypes.util, sys; raise SystemExit(0 if ctypes.util.find_library("portaudio") else 1)' 2>/dev/null \
    || MISSING+=("PortAudio: Debian/Ubuntu 'libportaudio2', Fedora 'portaudio', Arch 'portaudio'")
# Qt 6 (PySide6) on X11 and XWayland needs xcb-cursor.
"$SYSTEM_PY" -c 'import ctypes.util, sys; raise SystemExit(0 if ctypes.util.find_library("xcb-cursor") else 1)' 2>/dev/null \
    || MISSING+=("xcb-cursor: Debian/Ubuntu 'libxcb-cursor0', Fedora/Arch 'xcb-util-cursor'")

if [ "${#MISSING[@]}" -gt 0 ]; then
    echo "These system packages are needed before the Bridge can run:"
    for item in "${MISSING[@]}"; do echo "  - $item"; done
    echo
    [ "$MODE" = "paths" ] || [ "$MODE" = "input" ] || fail "Install the packages above, then run this script again."
fi
[ "$MODE" = "check" ] && { log "System check passed."; exit 0; }

# --- Where Elite's files are --------------------------------------------------------
echo "Detected locations:"
"$SYSTEM_PY" "$APP_ROOT/common/eab_platform.py" | sed 's/^/  /'
echo
if [ "$MODE" = "paths" ]; then exit 0; fi
if [ "$MODE" = "input" ]; then
    echo "Cockpit key sending:"
    "$SYSTEM_PY" "$APP_ROOT/common/eab_linux_input.py" | sed 's/^/  /'
    echo
    echo "A press test types 'elite ai bridge' into the active window 1.5 s after you run:"
    echo "  $SYSTEM_PY \"$APP_ROOT/common/eab_linux_input.py\" --press-test"
    echo "A hotkey test prints every Ctrl+Alt+Shift+<key> chord it sees for 15 s:"
    echo "  $SYSTEM_PY \"$APP_ROOT/common/eab_linux_input.py\" --hotkey-test"
    exit 0
fi
# Cockpit actions need a virtual keyboard (/dev/uinput) and X11 tools. Warn, do not stop:
# the dashboard, data, voice and AI work without them.
INPUT_WARN="$("$SYSTEM_PY" - <<'PY'
import sys; sys.path.insert(0, "common"); import eab_linux_input as m
ok, why = m.uinput_status()
if not ok: print("cockpit actions: " + why)
w = m.X11Windows()
if not w.can_query: print("cockpit actions: " + w.missing_tools_hint())
ok, why = m.keyboard_access_status()
if not ok: print("hotkeys and keyboard push to talk: " + why)
PY
)"
if [ -n "$INPUT_WARN" ]; then
    echo "NOTE: some keyboard features are off until this is fixed:"
    printf '%s\n' "$INPUT_WARN" | sed 's/^/      /'
    echo "      See LINUX.md, 'Cockpit key sending'. Run with --input to re-check."
    echo
fi
if ! "$SYSTEM_PY" -c 'import sys; sys.path.insert(0, "common"); import eab_platform; raise SystemExit(0 if eab_platform.journal_dir().is_dir() else 1)'; then
    echo "NOTE: the Elite journal folder was not found. Run Elite Dangerous once under Proton, or"
    echo "      set ELITE_JOURNAL_DIR / ELITE_PROTON_PREFIX (see LINUX.md). Starting anyway."
    echo
fi

# --- 2. Private runtime -------------------------------------------------------------
NEED_SETUP=0
[ "$MODE" = "setup" ] && NEED_SETUP=1
[ -f "$READY_MARKER" ] || NEED_SETUP=1
[ -x "$VENV_PY" ] || NEED_SETUP=1
if [ "$NEED_SETUP" = "0" ]; then
    "$VENV_PY" -c 'import PySide6, zmq, pygame, sounddevice, supertonic' >/dev/null 2>&1 || NEED_SETUP=1
fi

if [ "$NEED_SETUP" = "1" ]; then
    echo "Preparing the private runtime and the Supertonic voice..."
    echo "This takes several minutes on the first run (about 300 MB of packages and a 400 MB voice model)."
    echo
    export PYTHONUNBUFFERED=1
    # Plain HTTPS downloads for the voice model (the Xet transfer stalled silently on a test install).
    export HF_HUB_DISABLE_XET=1

    # A previous failed setup can leave a half-built venv behind. Never trust it.
    if [ -d "$VENV" ] && [ ! -f "$READY_MARKER" ] || [ "$MODE" = "setup" ]; then
        log "Rebuilding the private runtime cleanly..."
        rm -rf "$VENV" "$READY_MARKER"
    fi
    mkdir -p "$RUNTIME_DIR"

    log "Step 1 of 4: Creating the Bridge's private runtime in $VENV"
    [ -x "$VENV_PY" ] || "$SYSTEM_PY" -m venv "$VENV" || fail "Could not create the private Bridge runtime."

    log "Step 2 of 4: Downloading and installing components..."
    "$VENV_PY" -m pip install --disable-pip-version-check --upgrade pip 2>&1 | tee -a "$SETUP_LOG" | tail -n 1 \
        || fail "Could not prepare pip."
    # Exact versions: constraints.txt pins every package the runtime pulls in.
    PIN_ARG=()
    [ -f "$APP_ROOT/constraints.txt" ] && PIN_ARG=(-c "$APP_ROOT/constraints.txt")
    "$VENV_PY" -m pip install --disable-pip-version-check --progress-bar off \
        -r "$APP_ROOT/requirements.txt" "${PIN_ARG[@]}" 2>&1 | tee -a "$SETUP_LOG" | grep -E '^(Collecting|Installing|Successfully|ERROR)' \
        || true
    "$VENV_PY" -c 'import PySide6, zmq, pygame, sounddevice, supertonic' 2>>"$SETUP_LOG" \
        || fail "A required Bridge component failed to install."

    log "Step 3 of 4: Checking the components... OK"

    log "Step 4 of 4: Downloading the ship's voice (Supertonic 3 from Hugging Face)..."
    "$VENV_PY" -c "from supertonic import TTS; TTS(model='supertonic-3', auto_download=True); print('Supertonic neural voice ready.')" 2>&1 | tee -a "$SETUP_LOG" | tail -n 3 \
        || fail "Supertonic installed, but its neural voice model could not be prepared."

    echo ready > "$READY_MARKER"
    log "Runtime setup completed successfully."
    echo
fi

# --- 3. Launch ------------------------------------------------------------------------
# Elite under Proton puts its window on X11/XWayland; the overlay and screen placement
# behave best when the Bridge uses the same windowing path.
if [ -z "${QT_QPA_PLATFORM:-}" ] && [ -n "${WAYLAND_DISPLAY:-}" ] && [ -n "${DISPLAY:-}" ]; then
    export QT_QPA_PLATFORM=xcb
fi
export PYTHONUNBUFFERED=1
echo "Launching Elite AI Bridge..."
echo "If the app closes, the Python error will remain in this window (and in $DATA_DIR/qml_backend.log)."
echo
exec "$VENV_PY" "$APP_ROOT/frontend/main.py" "$@"
