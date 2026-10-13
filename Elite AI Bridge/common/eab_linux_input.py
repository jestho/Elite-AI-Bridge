"""Linux cockpit key sending for Elite AI Bridge (Elite Dangerous under Proton).

On Windows the Bridge presses cockpit keys with SendInput and hardware scan codes.
On Linux the equivalent is a virtual keyboard created through the kernel's uinput
interface: the game, Wine and the display server all see it as a real USB keyboard,
so it works the same on X11 and on Wayland (XWayland), without any helper daemon.

Two things are needed on the machine:

  * write access to /dev/uinput (one udev rule plus the "input" group, see LINUX.md);
  * for the "is Elite the active window" safety check and for bringing Elite to the
    front, the X11 tools `xdotool` (preferred) or `xprop` + `wmctrl`. Proton draws the
    game through X11/XWayland, so these work on Wayland desktops too.

This module is standard-library only. UinputKeyboard talks to the kernel directly
(ioctl + write) instead of depending on python-evdev, which would need a compiler
on the user's machine.
"""
from __future__ import annotations

import fcntl
import os
import shutil
import struct
import subprocess
import threading
import time
from pathlib import Path

UINPUT_PATH = "/dev/uinput"

# --- Linux input event codes (linux/input-event-codes.h) -----------------------------
EV_SYN = 0x00
EV_KEY = 0x01
SYN_REPORT = 0

KEY = {
    "ESC": 1, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10, "0": 11,
    "MINUS": 12, "EQUAL": 13, "BACKSPACE": 14, "TAB": 15,
    "Q": 16, "W": 17, "E": 18, "R": 19, "T": 20, "Y": 21, "U": 22, "I": 23, "O": 24, "P": 25,
    "LEFTBRACE": 26, "RIGHTBRACE": 27, "ENTER": 28, "LEFTCTRL": 29,
    "A": 30, "S": 31, "D": 32, "F": 33, "G": 34, "H": 35, "J": 36, "K": 37, "L": 38,
    "SEMICOLON": 39, "APOSTROPHE": 40, "GRAVE": 41, "LEFTSHIFT": 42, "BACKSLASH": 43,
    "Z": 44, "X": 45, "C": 46, "V": 47, "B": 48, "N": 49, "M": 50,
    "COMMA": 51, "DOT": 52, "SLASH": 53, "RIGHTSHIFT": 54, "KPASTERISK": 55, "LEFTALT": 56,
    "SPACE": 57, "CAPSLOCK": 58,
    "F1": 59, "F2": 60, "F3": 61, "F4": 62, "F5": 63, "F6": 64, "F7": 65, "F8": 66, "F9": 67, "F10": 68,
    "NUMLOCK": 69, "SCROLLLOCK": 70,
    "KP7": 71, "KP8": 72, "KP9": 73, "KPMINUS": 74, "KP4": 75, "KP5": 76, "KP6": 77, "KPPLUS": 78,
    "KP1": 79, "KP2": 80, "KP3": 81, "KP0": 82, "KPDOT": 83,
    "F11": 87, "F12": 88, "KPENTER": 96, "RIGHTCTRL": 97, "KPSLASH": 98, "SYSRQ": 99, "RIGHTALT": 100,
    "HOME": 102, "UP": 103, "PAGEUP": 104, "LEFT": 105, "RIGHT": 106, "END": 107, "DOWN": 108,
    "PAGEDOWN": 109, "INSERT": 110, "DELETE": 111, "PAUSE": 119,
    "LEFTMETA": 125, "RIGHTMETA": 126, "COMPOSE": 127,
    "F13": 183, "F14": 184, "F15": 185, "F16": 186, "F17": 187, "F18": 188,
    "F19": 189, "F20": 190, "F21": 191, "F22": 192, "F23": 193, "F24": 194,
}
KEY_MAX = 0x2FF

# Elite .binds keyboard tokens that are not simply Key_<letter/digit/Fn/Numpad_n>.
ELITE_SPECIAL = {
    "Key_Backspace": "BACKSPACE", "Key_Tab": "TAB", "Key_Enter": "ENTER",
    "Key_LeftShift": "LEFTSHIFT", "Key_RightShift": "RIGHTSHIFT",
    "Key_LeftControl": "LEFTCTRL", "Key_RightControl": "RIGHTCTRL",
    "Key_LeftAlt": "LEFTALT", "Key_RightAlt": "RIGHTALT",
    "Key_LeftWin": "LEFTMETA", "Key_RightWin": "RIGHTMETA", "Key_Apps": "COMPOSE",
    "Key_Escape": "ESC", "Key_Space": "SPACE", "Key_CapsLock": "CAPSLOCK",
    "Key_PageUp": "PAGEUP", "Key_PageDown": "PAGEDOWN", "Key_End": "END", "Key_Home": "HOME",
    "Key_LeftArrow": "LEFT", "Key_UpArrow": "UP", "Key_RightArrow": "RIGHT", "Key_DownArrow": "DOWN",
    "Key_Insert": "INSERT", "Key_Delete": "DELETE",
    "Key_ScrollLock": "SCROLLLOCK", "Key_NumLock": "NUMLOCK", "Key_Pause": "PAUSE",
    "Key_PrintScreen": "SYSRQ",
    "Key_SemiColon": "SEMICOLON", "Key_Equals": "EQUAL", "Key_Comma": "COMMA", "Key_Minus": "MINUS",
    "Key_Period": "DOT", "Key_Slash": "SLASH", "Key_Grave": "GRAVE",
    "Key_LeftBracket": "LEFTBRACE", "Key_BackSlash": "BACKSLASH", "Key_RightBracket": "RIGHTBRACE",
    "Key_Apostrophe": "APOSTROPHE",
    "Key_Numpad_Add": "KPPLUS", "Key_Numpad_Subtract": "KPMINUS", "Key_Numpad_Multiply": "KPASTERISK",
    "Key_Numpad_Divide": "KPSLASH", "Key_Numpad_Decimal": "KPDOT", "Key_Numpad_Enter": "KPENTER",
}


def keycode_for_elite_token(token: str) -> int:
    """Translate an Elite .binds keyboard token (Key_A, Key_F3, Key_Numpad_7...) to a KEY_* code."""
    token = str(token or "")
    if token in ELITE_SPECIAL:
        return KEY[ELITE_SPECIAL[token]]
    if token.startswith("Key_"):
        body = token[4:]
        if len(body) == 1 and (body.isalpha() or body.isdigit()):
            return KEY[body.upper()]
        if body.startswith("F") and body[1:].isdigit() and 1 <= int(body[1:]) <= 24:
            return KEY[body]
        if body.startswith("Numpad_") and body[7:].isdigit() and 0 <= int(body[7:]) <= 9:
            return KEY["KP" + body[7:]]
    raise ValueError(f"Unsupported keyboard token: {token}")


# --- uinput ----------------------------------------------------------------------------

def _ioc(direction: int, type_char: str, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord(type_char) << 8) | nr


_IOC_WRITE = 1
UI_DEV_CREATE = _ioc(0, "U", 1, 0)
UI_DEV_DESTROY = _ioc(0, "U", 2, 0)
_UINPUT_SETUP = struct.Struct("HHHH80sI")  # struct input_id + name[UINPUT_MAX_NAME_SIZE] + ff_effects_max
UI_DEV_SETUP = _ioc(_IOC_WRITE, "U", 3, _UINPUT_SETUP.size)
UI_SET_EVBIT = _ioc(_IOC_WRITE, "U", 100, 4)
UI_SET_KEYBIT = _ioc(_IOC_WRITE, "U", 101, 4)
_INPUT_EVENT = struct.Struct("llHHi")  # struct timeval + type + code + value
BUS_USB = 0x03


def uinput_status() -> tuple[bool, str]:
    """(usable, reason). Checks only the device node, never creates a keyboard."""
    if not os.path.exists(UINPUT_PATH):
        return False, (f"{UINPUT_PATH} does not exist: the uinput kernel module is not loaded "
                       "(sudo modprobe uinput; see LINUX.md to load it at boot)")
    if not os.access(UINPUT_PATH, os.W_OK):
        return False, (f"no write access to {UINPUT_PATH}: add the udev rule from LINUX.md and "
                       "put your user in the 'input' group, then log out and in")
    return True, ""


class UinputKeyboard:
    """A virtual USB keyboard. Created on first use and kept for the process lifetime."""

    def __init__(self, name: str = "Elite AI Bridge virtual keyboard"):
        self.name = name
        self._fd: int | None = None
        self._lock = threading.Lock()
        self._held: set[int] = set()

    def open(self) -> None:
        with self._lock:
            if self._fd is not None:
                return
            ok, why = uinput_status()
            if not ok:
                raise RuntimeError(why)
            fd = os.open(UINPUT_PATH, os.O_WRONLY | os.O_NONBLOCK)
            try:
                fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
                # Announce every key code so the display server treats the device as a
                # full keyboard (a device with only a few keys is often ignored).
                for code in range(1, KEY_MAX + 1):
                    fcntl.ioctl(fd, UI_SET_KEYBIT, code)
                setup = _UINPUT_SETUP.pack(BUS_USB, 0x1209, 0x3B01, 0x0100,
                                           self.name.encode("utf-8")[:79], 0)
                fcntl.ioctl(fd, UI_DEV_SETUP, setup)
                fcntl.ioctl(fd, UI_DEV_CREATE)
            except Exception:
                os.close(fd)
                raise
            self._fd = fd
        # The display server and Wine pick the new device up asynchronously. Give them
        # a moment once, or the first key press after start is lost.
        time.sleep(0.8)

    def close(self) -> None:
        with self._lock:
            if self._fd is None:
                return
            try:
                for code in sorted(self._held):
                    self._write(code, 0)
            except Exception:
                pass
            try:
                fcntl.ioctl(self._fd, UI_DEV_DESTROY)
            except Exception:
                pass
            os.close(self._fd)
            self._fd = None
            self._held.clear()

    def _write(self, code: int, value: int) -> None:
        if self._fd is None:
            raise RuntimeError("virtual keyboard is not open")
        now = time.time()
        sec, usec = int(now), int((now - int(now)) * 1_000_000)
        payload = (_INPUT_EVENT.pack(sec, usec, EV_KEY, code, value)
                   + _INPUT_EVENT.pack(sec, usec, EV_SYN, SYN_REPORT, 0))
        written = os.write(self._fd, payload)
        if written != len(payload):
            raise RuntimeError(f"short write to {UINPUT_PATH} ({written} of {len(payload)} bytes)")

    def key(self, code: int, down: bool) -> None:
        code = int(code)
        if not 1 <= code <= KEY_MAX:
            raise ValueError(f"key code {code} is out of range")
        if self._fd is None:
            self.open()
        with self._lock:
            self._write(code, 1 if down else 0)
            if down:
                self._held.add(code)
            else:
                self._held.discard(code)


# --- X11 window helpers (Proton draws Elite through X11 / XWayland) ---------------------

def _run(cmd: list[str], timeout: float = 1.5) -> str:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False,
                            stdin=subprocess.DEVNULL)
        return cp.stdout if cp.returncode == 0 else ""
    except Exception:
        return ""


def _looks_like_elite(title: str) -> bool:
    low = str(title or "").lower()
    return "elite - dangerous" in low and "launcher" not in low


class X11Windows:
    """Active-window and activation queries through xdotool, or xprop + wmctrl."""

    def __init__(self):
        self.xdotool = shutil.which("xdotool")
        self.xprop = shutil.which("xprop")
        self.wmctrl = shutil.which("wmctrl")
        self._cache: tuple[float, str] = (0.0, "")

    @property
    def can_query(self) -> bool:
        return bool(os.environ.get("DISPLAY")) and bool(self.xdotool or self.xprop)

    @property
    def can_activate(self) -> bool:
        return bool(os.environ.get("DISPLAY")) and bool(self.xdotool or (self.xprop and self.wmctrl))

    def missing_tools_hint(self) -> str:
        if not os.environ.get("DISPLAY"):
            return "no X11 display (DISPLAY is not set); Elite under Proton needs X11 or XWayland"
        return "install 'xdotool' (or 'xprop' and 'wmctrl') so the Bridge can see which window is active"

    def _xprop_name(self, window_id: str) -> str:
        out = _run([self.xprop, "-id", window_id, "_NET_WM_NAME", "WM_NAME"])
        for line in out.splitlines():
            if "=" in line and '"' in line:
                return line.split("=", 1)[1].strip().strip('"').replace('\\"', '"')
        return ""

    def active_title(self, max_age: float = 0.1) -> str:
        now = time.monotonic()
        stamp, title = self._cache
        if now - stamp < max_age:
            return title
        title = ""
        if self.xdotool:
            title = _run([self.xdotool, "getactivewindow", "getwindowname"]).strip()
        elif self.xprop:
            out = _run([self.xprop, "-root", "_NET_ACTIVE_WINDOW"])
            if "#" in out:
                window_id = out.split("#", 1)[1].strip().split()[0].rstrip(",")
                if window_id not in ("0x0", "0"):
                    title = self._xprop_name(window_id)
        self._cache = (now, title)
        return title

    def find_elite(self) -> tuple[str, str]:
        """(window id, title) of the running game, or ("", "")."""
        if self.xdotool:
            ids = _run([self.xdotool, "search", "--onlyvisible", "--name", "Elite - Dangerous"]).split()
            for window_id in ids:
                title = _run([self.xdotool, "getwindowname", window_id]).strip()
                if _looks_like_elite(title):
                    return window_id, title
            return "", ""
        if self.xprop:
            out = _run([self.xprop, "-root", "_NET_CLIENT_LIST"])
            if "#" in out:
                for window_id in out.split("#", 1)[1].replace(",", " ").split():
                    title = self._xprop_name(window_id)
                    if _looks_like_elite(title):
                        return window_id, title
        return "", ""

    def activate(self, window_id: str) -> bool:
        if self.xdotool:
            cmd = [self.xdotool, "windowactivate", "--sync", window_id]
        elif self.wmctrl:
            cmd = [self.wmctrl, "-i", "-a", window_id]
        else:
            return False
        try:
            return subprocess.run(cmd, capture_output=True, timeout=3.0, check=False,
                                  stdin=subprocess.DEVNULL).returncode == 0
        except Exception:
            return False


# --- Global hotkeys and hold-to-talk: reading the real keyboards -----------------------
#
# Windows registers chords with RegisterHotKey. Linux has no desktop-neutral equivalent,
# so the Bridge reads the keyboards themselves through /dev/input/event* (the evdev
# interface, the mirror image of uinput above). That works on X11 and Wayland, whatever
# window is focused, and reports key release, which is what hold-to-talk needs. The same
# "input" group that allows /dev/uinput gives read access to these devices on every
# common distribution. Keys are never grabbed, so Elite still sees them; the Setup page
# already refuses a chord that Elite uses.

EV_KEY_VALUE_UP, EV_KEY_VALUE_DOWN, EV_KEY_VALUE_REPEAT = 0, 1, 2
INPUT_DEVICES_PROC = "/proc/bus/input/devices"
INPUT_DEV_DIR = "/dev/input"

MODIFIER_KEYS = {
    KEY["LEFTCTRL"]: "CTRL", KEY["RIGHTCTRL"]: "CTRL",
    KEY["LEFTALT"]: "ALT", KEY["RIGHTALT"]: "ALT",
    KEY["LEFTSHIFT"]: "SHIFT", KEY["RIGHTSHIFT"]: "SHIFT",
    KEY["LEFTMETA"]: "WIN", KEY["RIGHTMETA"]: "WIN",
}
_MOD_WORDS = {"CTRL": "CTRL", "CONTROL": "CTRL", "ALT": "ALT", "SHIFT": "SHIFT", "WIN": "WIN", "META": "WIN", "SUPER": "WIN"}

# Windows virtual-key codes (what the Bridge stores for a hotkey) -> KEY_* codes.
VK_TO_KEY = {
    0x08: "BACKSPACE", 0x09: "TAB", 0x0D: "ENTER", 0x13: "PAUSE", 0x14: "CAPSLOCK", 0x1B: "ESC",
    0x20: "SPACE", 0x21: "PAGEUP", 0x22: "PAGEDOWN", 0x23: "END", 0x24: "HOME",
    0x25: "LEFT", 0x26: "UP", 0x27: "RIGHT", 0x28: "DOWN", 0x2C: "SYSRQ", 0x2D: "INSERT", 0x2E: "DELETE",
    0x5D: "COMPOSE", 0x6A: "KPASTERISK", 0x6B: "KPPLUS", 0x6D: "KPMINUS", 0x6E: "KPDOT", 0x6F: "KPSLASH",
    0x90: "NUMLOCK", 0x91: "SCROLLLOCK",
    0xBA: "SEMICOLON", 0xBB: "EQUAL", 0xBC: "COMMA", 0xBD: "MINUS", 0xBE: "DOT", 0xBF: "SLASH", 0xC0: "GRAVE",
    0xDB: "LEFTBRACE", 0xDC: "BACKSLASH", 0xDD: "RIGHTBRACE", 0xDE: "APOSTROPHE",
}
VK_TO_KEY.update({0x30 + n: str(n) for n in range(10)})
VK_TO_KEY.update({0x41 + n: chr(ord("A") + n) for n in range(26)})
VK_TO_KEY.update({0x60 + n: f"KP{n}" for n in range(10)})
VK_TO_KEY.update({0x70 + n: f"F{n + 1}" for n in range(24)})

# The key names the Setup page shows ("Num 7", "Page Up", "Num Enter"...) -> KEY_* names.
_DISPLAY_KEY = {
    "PAGEUP": "PAGEUP", "PAGEDOWN": "PAGEDOWN", "END": "END", "HOME": "HOME",
    "LEFT": "LEFT", "UP": "UP", "RIGHT": "RIGHT", "DOWN": "DOWN", "INSERT": "INSERT", "DELETE": "DELETE",
    "SPACE": "SPACE", "TAB": "TAB", "ENTER": "ENTER", "RETURN": "ENTER", "NUMENTER": "KPENTER",
    "BACKSPACE": "BACKSPACE", "ESC": "ESC", "ESCAPE": "ESC",
}


def keycode_for_hotkey(display: str, vk: int) -> int:
    """KEY_* code for a Bridge hotkey spec. The display's key name wins (it tells
    "Num Enter" from "Enter"); the Windows virtual-key code is the fallback."""
    name = str(display or "").split("+")[-1].strip().upper().replace(" ", "")
    if name in _DISPLAY_KEY:
        return KEY[_DISPLAY_KEY[name]]
    if name.startswith("NUM") and name[3:].isdigit():
        return KEY["KP" + name[3:]]
    if name in KEY and (len(name) == 1 or name.startswith("F")):
        return KEY[name]
    if int(vk or 0) in VK_TO_KEY:
        return KEY[VK_TO_KEY[int(vk)]]
    raise ValueError(f"Unsupported hotkey {display!r} (vk 0x{int(vk or 0):02X})")


def modifiers_for_hotkey(display: str) -> frozenset:
    """The modifier set a chord's display names, e.g. "Ctrl+Alt+Shift+P" -> {CTRL, ALT, SHIFT}."""
    return frozenset(_MOD_WORDS[p.strip().upper()] for p in str(display or "").split("+")[:-1]
                     if p.strip().upper() in _MOD_WORDS)


def _bitmap_has(words: list[str], bit: int) -> bool:
    # /proc prints the bitmap as 64-bit hex words, most significant first.
    try:
        index = bit // 64
        word = int(words[len(words) - 1 - index], 16) if index < len(words) else 0
        return bool(word >> (bit % 64) & 1)
    except Exception:
        return False


def list_keyboards(proc_path: str = INPUT_DEVICES_PROC) -> list[dict]:
    """Keyboards from /proc/bus/input/devices: [{name, node, readable}], own virtual one excluded."""
    try:
        text = Path(proc_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    found = []
    for block in text.split("\n\n"):
        name, handlers, ev_bits, key_words = "", "", "0", []
        for line in block.splitlines():
            if line.startswith("N: Name="):
                name = line[8:].strip().strip('"')
            elif line.startswith("H: Handlers="):
                handlers = line[12:]
            elif line.startswith("B: EV="):
                ev_bits = line[6:].strip()
            elif line.startswith("B: KEY="):
                key_words = line[7:].split()
        event = next((h for h in handlers.split() if h.startswith("event")), "")
        if not event or not name:
            continue
        try:
            has_ev_key = bool(int(ev_bits, 16) >> EV_KEY & 1)
        except Exception:
            has_ev_key = False
        # A keyboard has letters and a modifier; this skips mice, pads, power buttons, HOTAS.
        if not has_ev_key or not all(_bitmap_has(key_words, KEY[k]) for k in ("A", "Z", "LEFTSHIFT", "ENTER")):
            continue
        if name.startswith("Elite AI Bridge"):
            continue
        node = os.path.join(INPUT_DEV_DIR, event)
        found.append({"name": name, "node": node, "readable": os.access(node, os.R_OK)})
    return found


def keyboard_access_status() -> tuple[bool, str]:
    """(usable, reason) for reading the keyboards. Never opens a device."""
    boards = list_keyboards()
    if not boards:
        return False, "no keyboard found in /proc/bus/input/devices"
    if not any(b["readable"] for b in boards):
        return False, ("no read access to /dev/input/event*: put your user in the 'input' group "
                       "(see LINUX.md), then log out and in")
    return True, ""


class LinuxHotkeyListener:
    """Watches every keyboard for Bridge chords. Same shape as the engine's
    BridgeGlobalHotkeys: specs of (command_id, display, vk, label), a queue that
    receives command ids on key-down, plus `registered`, `failures` and `status`.

    is_pressed(command_id) answers whether the chord's key is physically held, which
    is what keyboard hold-to-talk polls for release. Chords need their exact modifier
    set, as RegisterHotKey does, and auto-repeat never re-fires a command.
    """

    RESCAN_SECONDS = 3.0

    def __init__(self, specs, output_queue, force_modifiers=frozenset({"CTRL", "ALT", "SHIFT"}), free_keys=None):
        self.specs = tuple(specs or ())
        self.output_queue = output_queue
        self.force_modifiers = frozenset(force_modifiers or ())
        # keys allowed without a modifier (F13..F24 on Windows: HOTAS software emits them)
        self.free_keys = set(free_keys if free_keys is not None else (KEY[f"F{n}"] for n in range(13, 25)))
        self.registered: dict[str, str] = {}
        self.failures: dict[str, dict] = {}
        self.status = "Not started"
        self.thread: threading.Thread | None = None
        self.running = False
        self._chords: dict[int, list[tuple[frozenset, str]]] = {}   # keycode -> [(modifiers, command_id)]
        self._command_key: dict[str, int] = {}
        self._pressed: set[int] = set()
        self._lock = threading.Lock()
        self._wake_r, self._wake_w = os.pipe()
        self._devices: dict[str, int] = {}  # node -> fd
        self.keyboards_seen = 0

    # -- setup ---------------------------------------------------------------------
    def _compile(self) -> None:
        self._chords.clear()
        self._command_key.clear()
        self.registered.clear()
        self.failures.clear()
        seen: dict[tuple[int, frozenset], str] = {}
        for command_id, display, vk, _label in self.specs:
            try:
                code = keycode_for_hotkey(display, vk)
                mods = modifiers_for_hotkey(display)
                if not mods and code not in self.free_keys:
                    mods = self.force_modifiers  # never take a plain key from the game
                if (code, mods) in seen:
                    raise ValueError(f"same chord as {seen[(code, mods)]}")
                seen[(code, mods)] = command_id
            except Exception as exc:
                self.failures[command_id] = {"display": display, "error": str(exc)}
                continue
            self._chords.setdefault(code, []).append((mods, command_id))
            self._command_key[command_id] = code
            self.registered[command_id] = display

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self._compile()
        ok, why = keyboard_access_status()
        if not ok:
            self.registered.clear()
            self.failures = {cid: {"display": disp, "error": why} for cid, disp, _vk, _l in self.specs}
            self.status = f"0/{len(self.specs)} Bridge hotkeys active: {why}"
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, name="EliteBridge-LinuxHotkeys", daemon=True)
        self.thread.start()
        self.status = f"{len(self.registered)}/{len(self.specs)} Bridge hotkeys active on all keyboards."
        if self.failures:
            self.status += " Some shortcuts could not be mapped."

    def stop(self) -> None:
        self.running = False
        try:
            os.write(self._wake_w, b"x")
        except Exception:
            pass
        t = self.thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(1.5)

    def is_pressed(self, command_id: str) -> bool:
        code = self._command_key.get(str(command_id))
        with self._lock:
            return bool(code is not None and code in self._pressed and self.running)

    # -- the reader thread -----------------------------------------------------------
    def _rescan(self) -> None:
        wanted = {b["node"] for b in list_keyboards() if b["readable"]}
        for node in list(self._devices):
            if node not in wanted:
                self._close(node)
        for node in wanted - set(self._devices):
            try:
                self._devices[node] = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
            except Exception:
                pass
        self.keyboards_seen = len(self._devices)

    def _close(self, node: str) -> None:
        fd = self._devices.pop(node, None)
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass

    def _run(self) -> None:
        import select
        last_scan = 0.0
        try:
            while self.running:
                now = time.monotonic()
                if now - last_scan >= self.RESCAN_SECONDS:
                    self._rescan()
                    last_scan = now
                fds = list(self._devices.values()) + [self._wake_r]
                try:
                    ready, _, _ = select.select(fds, [], [], self.RESCAN_SECONDS)
                except Exception:
                    time.sleep(0.2)
                    continue
                for fd in ready:
                    if fd == self._wake_r:
                        try:
                            os.read(self._wake_r, 64)
                        except Exception:
                            pass
                        continue
                    node = next((n for n, f in self._devices.items() if f == fd), None)
                    try:
                        data = os.read(fd, _INPUT_EVENT.size * 64)
                    except BlockingIOError:
                        continue
                    except Exception:
                        if node:
                            self._close(node)  # unplugged
                        continue
                    for offset in range(0, len(data) - _INPUT_EVENT.size + 1, _INPUT_EVENT.size):
                        _sec, _usec, etype, code, value = _INPUT_EVENT.unpack_from(data, offset)
                        if etype == EV_KEY:
                            self._on_key(code, value)
        finally:
            for node in list(self._devices):
                self._close(node)
            with self._lock:
                self._pressed.clear()

    def _on_key(self, code: int, value: int) -> None:
        if value == EV_KEY_VALUE_REPEAT:
            return
        with self._lock:
            if value == EV_KEY_VALUE_DOWN:
                self._pressed.add(code)
            else:
                self._pressed.discard(code)
            held_mods = frozenset(MODIFIER_KEYS[k] for k in self._pressed if k in MODIFIER_KEYS)
        if value != EV_KEY_VALUE_DOWN or code in MODIFIER_KEYS:
            return
        for mods, command_id in self._chords.get(code, ()):
            if mods == held_mods:
                self.output_queue.put(command_id)
                break


# --- Diagnostics ---------------------------------------------------------------------

def describe() -> dict[str, str]:
    ok, why = uinput_status()
    win = X11Windows()
    elite_id, elite_title = win.find_elite() if win.can_query else ("", "")
    kb_ok, kb_why = keyboard_access_status()
    boards = list_keyboards()
    return {
        "uinput": "ready" if ok else why,
        "keyboards": (f"{sum(1 for b in boards if b['readable'])}/{len(boards)} readable: "
                      + ", ".join(b["name"] for b in boards)) if kb_ok else kb_why,
        "display": os.environ.get("DISPLAY", "") or "(not set)",
        "session": os.environ.get("XDG_SESSION_TYPE", "") or "(unknown)",
        "xdotool": win.xdotool or "(not found)",
        "xprop": win.xprop or "(not found)",
        "wmctrl": win.wmctrl or "(not found)",
        "active_window": (win.active_title() or "(none)") if win.can_query else "(cannot query)",
        "elite_window": (f"{elite_title} [{elite_id}]" if elite_id else "(not running)") if win.can_query else "(cannot query)",
    }


if __name__ == "__main__":
    import sys
    for key, value in describe().items():
        print(f"{key:14} {value}")
    if "--hotkey-test" in sys.argv:
        # Prints every Bridge default chord it sees for 15 seconds (Ctrl+Alt+Shift+P ...).
        import queue as _queue
        q: "_queue.Queue[str]" = _queue.Queue()
        specs = [(f"key_{ch}", f"Ctrl+Alt+Shift+{ch}", ord(ch), ch) for ch in "PTCDLJ123456789EXV"]
        listener = LinuxHotkeyListener(specs, q)
        listener.start()
        print(listener.status)
        print("Press Ctrl+Alt+Shift+<letter or digit> anywhere; watching for 15 s...")
        end = time.time() + 15
        while time.time() < end:
            try:
                cmd = q.get(timeout=0.5)
                print("  chord:", cmd, "(still held)" if listener.is_pressed(cmd) else "")
            except _queue.Empty:
                pass
        listener.stop()
        print("done")
    if "--press-test" in sys.argv:
        # Types "elite ai bridge" into whatever window is active, 1.5 s from now.
        print("Press test: focus a text field now...")
        time.sleep(1.5)
        kb = UinputKeyboard()
        for ch in "elite ai bridge":
            code = KEY["SPACE"] if ch == " " else KEY[ch.upper()]
            kb.key(code, True); time.sleep(0.03); kb.key(code, False); time.sleep(0.03)
        kb.close()
        print("done")
