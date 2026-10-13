"""Per-platform locations for Elite AI Bridge.

Windows keeps the 2.0.0 layout exactly: Bridge data under %LOCALAPPDATA%\\EliteAIBridge,
the Elite journal under "Saved Games" in the user profile, bindings under
%LOCALAPPDATA%\\Frontier Developments.

On Linux, Elite Dangerous runs under Steam Proton and keeps its files inside the
game's Wine prefix (Steam app id 359320):

    <steam library>/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/
        Saved Games/Frontier Developments/Elite Dangerous/          (journal, Status.json)
        AppData/Local/Frontier Developments/Elite Dangerous/Options/  (Bindings, Graphics)

This module finds that prefix (every Steam library listed in libraryfolders.vdf is
checked) and keeps Bridge data under $XDG_DATA_HOME/EliteAIBridge. Everything can be
overridden with environment variables, which the launch script may also set:

    ELITE_AI_BRIDGE_DATA_DIR   Bridge settings, logs, caches
    ELITE_PROTON_PREFIX        the "pfx" folder (or its compatdata/359320 parent)
    ELITE_JOURNAL_DIR          journal folder (wins over the prefix lookup)
    ELITE_BINDINGS_DIR         Options/Bindings folder (wins over the prefix lookup)

Both the frontend and the backend import this file, so a path is only computed in
one place. It must stay dependency-free (standard library only).
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ELITE_STEAM_APPID = "359320"
IS_WINDOWS = os.name == "nt"

_ELITE_SAVED_GAMES = ("Saved Games", "Frontier Developments", "Elite Dangerous")
_ELITE_OPTIONS = ("Frontier Developments", "Elite Dangerous", "Options")


def _env_path(name: str) -> Path | None:
    value = str(os.environ.get(name) or "").strip()
    return Path(value).expanduser() if value else None


def data_dir() -> Path:
    """Folder for Bridge settings, logs, caches and the custom sound library."""
    override = _env_path("ELITE_AI_BRIDGE_DATA_DIR")
    if override is not None:
        return override
    if IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "EliteAIBridge"
    xdg = str(os.environ.get("XDG_DATA_HOME") or "").strip()
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / "EliteAIBridge"


def data_dir_label() -> str:
    """The data folder the way a user would type it (for status messages)."""
    if IS_WINDOWS:
        return r"%LOCALAPPDATA%\EliteAIBridge"
    return str(data_dir())


# --- Steam / Proton -----------------------------------------------------------------

def steam_roots() -> list[Path]:
    """Steam install folders worth checking on this machine (existing ones only)."""
    home = Path.home()
    candidates = [
        _env_path("STEAM_DIR"),
        home / ".steam" / "steam",
        home / ".steam" / "root",
        home / ".local" / "share" / "Steam",
        home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",  # Flatpak
        home / "snap" / "steam" / "common" / ".local" / "share" / "Steam",  # Snap
    ]
    seen: set[Path] = set()
    roots: list[Path] = []
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            resolved = candidate.resolve()
        except Exception:
            continue
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        roots.append(resolved)
    return roots


def steam_libraries() -> list[Path]:
    """Every Steam library folder: the install roots plus those in libraryfolders.vdf."""
    libraries: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        try:
            resolved = path.resolve()
        except Exception:
            return
        if resolved not in seen and (resolved / "steamapps").is_dir():
            seen.add(resolved)
            libraries.append(resolved)

    for root in steam_roots():
        add(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            add(Path(match.group(1).replace("\\\\", "\\")))
    return libraries


def proton_prefix() -> Path | None:
    """The Wine prefix ("pfx" folder) of Elite Dangerous under Proton, if present."""
    override = _env_path("ELITE_PROTON_PREFIX")
    if override is not None:
        if override.name != "pfx" and (override / "pfx").is_dir():
            override = override / "pfx"
        return override
    if IS_WINDOWS:
        return None
    for library in steam_libraries():
        pfx = library / "steamapps" / "compatdata" / ELITE_STEAM_APPID / "pfx"
        if pfx.is_dir():
            return pfx
    return None


def proton_user_dir() -> Path | None:
    """drive_c/users/steamuser inside the Elite prefix (Proton's Windows user profile)."""
    pfx = proton_prefix()
    if pfx is None:
        return None
    users = pfx / "drive_c" / "users"
    for name in ("steamuser", os.environ.get("USER", ""), "Public"):
        if name and (users / name).is_dir():
            return users / name
    return users / "steamuser"


# --- Elite Dangerous folders --------------------------------------------------------

def journal_dir() -> Path:
    """Where Elite writes Journal.*.log, Status.json, Market.json and friends.

    The folder is returned even when it does not exist, so callers can show its
    path in an error. On Linux a plain ~/Saved Games/... (a symlink the user made)
    still wins over the Proton prefix, which keeps earlier workarounds working.
    """
    override = _env_path("ELITE_JOURNAL_DIR")
    if override is not None:
        return override
    native = Path.home().joinpath(*_ELITE_SAVED_GAMES)
    if IS_WINDOWS or native.is_dir():
        return native
    user = proton_user_dir()
    if user is not None:
        return user.joinpath(*_ELITE_SAVED_GAMES)
    return native


def options_dir() -> Path:
    """Elite's Options folder: Bindings/ and Graphics/DisplaySettings.xml live under it."""
    bindings = _env_path("ELITE_BINDINGS_DIR")
    if bindings is not None:
        return bindings.parent
    if IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", "")).joinpath(*_ELITE_OPTIONS)
    user = proton_user_dir()
    if user is not None:
        return user.joinpath("AppData", "Local", *_ELITE_OPTIONS)
    # No prefix found: a non-existent path, so "not found" checks stay truthful.
    return Path.home().joinpath(".local", "share", *_ELITE_OPTIONS)


def bindings_dir() -> Path:
    override = _env_path("ELITE_BINDINGS_DIR")
    return override if override is not None else options_dir() / "Bindings"


def display_settings_file() -> Path:
    return options_dir() / "Graphics" / "DisplaySettings.xml"


# --- OpenAI API key persistence -----------------------------------------------------

def api_key_file() -> Path:
    """Linux/macOS only: where the verified OpenAI key is kept between runs.

    Windows stores the key as the user's OPENAI_API_KEY environment variable instead
    (see backend_host._set_windows_user_api_key).
    """
    return data_dir() / "openai_api_key"


def load_persisted_api_key() -> bool:
    """Put a previously saved key into OPENAI_API_KEY. Returns True if one was loaded.

    An OPENAI_API_KEY already in the environment always wins.
    """
    if IS_WINDOWS or str(os.environ.get("OPENAI_API_KEY") or "").strip():
        return False
    try:
        value = api_key_file().read_text(encoding="utf-8").strip()
    except Exception:
        return False
    if not value:
        return False
    os.environ["OPENAI_API_KEY"] = value
    return True


def persist_api_key(value: str) -> Path:
    """Save the key for later runs (owner read/write only). Linux/macOS only."""
    value = str(value or "").strip()
    if not value:
        raise ValueError("API key cannot be blank.")
    path = api_key_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(value + "\n")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    return path


# --- Desktop helpers ----------------------------------------------------------------

def open_folder(path: Path | str, select: Path | str | None = None) -> bool:
    """Show a folder in the desktop file manager. Returns False when nothing could run."""
    try:
        if IS_WINDOWS:
            if select is not None:
                subprocess.Popen(["explorer.exe", f"/select,{select}"],
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        opener = "open" if os.uname().sysname == "Darwin" else "xdg-open"
        subprocess.Popen([opener, str(path)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def describe() -> dict[str, str]:
    """Resolved locations, for diagnostics and the launch script's --paths option."""
    pfx = proton_prefix()
    return {
        "platform": "windows" if IS_WINDOWS else os.uname().sysname.lower(),
        "data_dir": str(data_dir()),
        "proton_prefix": str(pfx) if pfx else "",
        "journal_dir": str(journal_dir()),
        "journal_found": "yes" if journal_dir().is_dir() else "no",
        "bindings_dir": str(bindings_dir()),
        "bindings_found": "yes" if bindings_dir().is_dir() else "no",
        "display_settings": str(display_settings_file()),
    }


if __name__ == "__main__":
    for key, value in describe().items():
        print(f"{key:17} {value}")
