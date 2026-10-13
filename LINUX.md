# Elite AI Bridge on Linux (Elite Dangerous under Proton)

Elite AI Bridge is a Windows application. This page describes the experimental native
Linux run of the same source, for pilots who play Elite Dangerous through Steam Proton.
It is a work in progress. The dashboard, data, voice and AI parts run. Cockpit actions
(the keys the Bridge presses in the game) work through a virtual keyboard once you have
set up `/dev/uinput` and the X11 tools described under "Cockpit key sending". See "What
does not work yet" before you spend time on it.

## What works
- The full interface: Flight Deck, Combat, Trade, Navigation, Colonization, Commander,
  Setup wizard and page tours.
- Live game state from the journal and Status.json inside the Proton prefix.
- Trade, bounty hunting, colonization and route searches (EDDN cache, EDData, Ardent
  Insight, INTRA, EDSM).
- The ship voice (Supertonic, local) and sound effects, through PortAudio.
- The optional OpenAI co-pilot, including push to talk on a HOTAS or controller button.
- The OpenAI key typed into the setup wizard is kept between runs.
- Cockpit actions: Dock, Launch, Clear and Jump, route plotting, station services, combat
  macros, Dynamic PIPs, auto chaff and the trade loop, after the one-time setup below.

- Bridge hotkeys (Ctrl+Alt+Shift+P and the rest) and keyboard push to talk, read from your
  keyboards directly, after the same one-time setup.

## What does not work yet
- **The Windows system voice fallback.** Only Supertonic is available. If its model
  failed to download, the Bridge is silent.
- **The in-game overlay on native Wayland.** Qt cannot place a window over another
  application on Wayland. The launcher selects X11 (XWayland) automatically when both are
  present, which is also where Proton draws the game.

## Requirements
- A 64-bit Linux desktop with X11 or XWayland.
- Python 3.12 or newer, with `venv` and `tkinter`.
- PortAudio and the Qt xcb-cursor library.

| Distribution | Packages |
|---|---|
| Debian, Ubuntu, Mint | `python3 python3-venv python3-tk libportaudio2 libxcb-cursor0` |
| Fedora | `python3 python3-tkinter portaudio xcb-util-cursor` |
| Arch, Manjaro | `python tk portaudio xcb-util-cursor` |

The launcher checks for these and names the missing ones. Internet access is needed on
the first run for about 300 MB of Python packages and the 400 MB Supertonic voice model.

## Quick start
1. Run Elite Dangerous once through Steam so that the Proton prefix and journal exist.
2. From the top folder of the source:

       ./RUN_CURRENT_SOURCE.sh

   The first run builds the Bridge's private runtime under
   `~/.local/share/EliteAIBridge/runtime` and downloads the voice model, then starts
   the Bridge. Later runs start at once.

Other launcher options:

    ./RUN_CURRENT_SOURCE.sh --check    check Python and system packages only
    ./RUN_CURRENT_SOURCE.sh --paths    show where the Bridge will look for Elite's files
    ./RUN_CURRENT_SOURCE.sh --setup    rebuild the private runtime from scratch

## Cockpit key sending
On Windows the Bridge presses cockpit keys with the `SendInput` API. On Linux it creates
a virtual USB keyboard through the kernel's uinput interface, so the game, Wine and the
display server see real key presses. This works on X11 and on Wayland desktops, because
Proton draws the game through X11 (XWayland) either way. Two one-time steps:

1. **Allow your user to create virtual input devices.** Save this udev rule, add yourself
   to the `input` group, make sure the module loads at boot, then log out and in:

       sudo tee /etc/udev/rules.d/80-elite-ai-bridge-uinput.rules >/dev/null <<'EOF'
       KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
       EOF
       echo uinput | sudo tee /etc/modules-load.d/uinput.conf >/dev/null
       sudo modprobe uinput
       sudo udevadm control --reload-rules && sudo udevadm trigger
       sudo usermod -aG input "$USER"

   Anyone in the `input` group can create virtual keyboards, which is the same access
   `ydotool` and similar tools need.

2. **Install `xdotool`** (or `xprop` and `wmctrl`). The Bridge only sends keys while the
   game is the active window, exactly as on Windows, and uses these tools to check that
   and to bring Elite to the front for route plotting. Without them every cockpit action
   is refused.

Check the result with:

    ./RUN_CURRENT_SOURCE.sh --input

It reports whether `/dev/uinput` is writable, which tools were found, the active window
and whether the Elite window is visible. The launcher prints the same warning at startup
while anything is missing; the rest of the Bridge keeps working in the meantime.

The Bridge's keyboard appears in the game as "Elite AI Bridge virtual keyboard". Elite
reads it like any other keyboard, so the keys come from your own `.binds` profile and
nothing needs to be rebound. On a Wayland desktop the active-window check only sees X11
windows (the game and the Bridge itself, which the launcher starts under XWayland), which
is enough for the safety check.

## Bridge hotkeys and keyboard push to talk
On Windows the Bridge shortcuts (Ctrl+Alt+Shift+P for Target Power Plant, Ctrl+Alt+Shift+V
for push to talk, and so on) are registered with the system. Linux desktops have no
shared way to do that, so the Bridge reads your keyboards directly through
`/dev/input/event*`, the counterpart of the virtual keyboard above. The `input` group
from step 1 is all it needs. It works on X11 and Wayland, whatever window is focused,
and it sees key release, so keyboard push to talk is real hold-to-talk.

Differences from Windows:

- The chords are not taken away from other programs. Elite also receives
  Ctrl+Alt+Shift+P, which it ignores unless you bound it; the Setup page refuses a Bridge
  shortcut that Elite already uses.
- Each key keeps the modifiers shown in Setup, with F13 to F24 usable bare (HOTAS software
  emits them). A key saved without a modifier is treated as Ctrl+Alt+Shift+key, as on
  Windows.
- Keyboards plugged in later are picked up within a few seconds.

`./RUN_CURRENT_SOURCE.sh --input` lists the keyboards it can read and prints a 15-second
hotkey test command. Setup > Controls shows NOT REGISTERED on every row while the
keyboards cannot be read.

## Where things are
Elite under Proton keeps its files inside the game's Wine prefix (Steam app id 359320).
The Bridge looks for that prefix in every Steam library listed in `libraryfolders.vdf`,
including Flatpak and Snap installs of Steam:

    <steam library>/steamapps/compatdata/359320/pfx/drive_c/users/steamuser/
        Saved Games/Frontier Developments/Elite Dangerous/           journal, Status.json
        AppData/Local/Frontier Developments/Elite Dangerous/Options/  Bindings, Graphics

The Bridge's own files (settings, logs, caches, custom sounds, the private runtime) live
in `$XDG_DATA_HOME/EliteAIBridge`, normally `~/.local/share/EliteAIBridge`.

If the automatic lookup does not find the game, set one of these before launching:

| Variable | Meaning |
|---|---|
| `ELITE_PROTON_PREFIX` | the `pfx` folder (or its `compatdata/359320` parent) |
| `ELITE_JOURNAL_DIR` | the journal folder directly; wins over the prefix lookup |
| `ELITE_BINDINGS_DIR` | the `Options/Bindings` folder directly |
| `ELITE_AI_BRIDGE_DATA_DIR` | where the Bridge keeps its own files |
| `STEAM_DIR` | an unusual Steam install folder |

A symlink at `~/Saved Games/Frontier Developments/Elite Dangerous` pointing into the
prefix also works and takes priority over the lookup.

## The OpenAI API key
On Windows the verified key is stored as the user's `OPENAI_API_KEY` environment
variable. Linux has no such store, so the Bridge writes it to
`~/.local/share/EliteAIBridge/openai_api_key` with owner-only permissions (mode 600) and
loads it back at startup. An `OPENAI_API_KEY` already set in the environment always wins.
Delete that file to forget the key.

## Troubleshooting
- **"Elite journal folder not found"** or the Bridge shows OFFLINE while the game runs:
  run `./RUN_CURRENT_SOURCE.sh --paths` and compare with your Steam library. Set
  `ELITE_PROTON_PREFIX` if the game is installed somewhere unusual.
- **No sound or no voice:** `libportaudio2` (or your distribution's PortAudio) must be
  installed before the runtime is built. Install it, then run with `--setup`.
- **Qt fails to start with an xcb error:** install `libxcb-cursor0` / `xcb-util-cursor`.
- **Dock, Launch or a route plot says "unavailable", "not the foreground window" or
  "Windows-only":** run `./RUN_CURRENT_SOURCE.sh --input`. Usually `/dev/uinput` is not
  writable yet (log out and in after adding the group) or `xdotool` is missing.
- **Setup > Controls shows every shortcut as NOT REGISTERED, or push to talk never
  starts:** the keyboards cannot be read. Run `./RUN_CURRENT_SOURCE.sh --input`; the
  usual cause is the `input` group not being active yet (log out and in).
- **Keys reach the desktop but not the game:** click into the game window once so it has
  keyboard focus, and check that Elite's own Options > Controls show your keyboard preset.
- **Logs:** `~/.local/share/EliteAIBridge/qml_backend.log` and
  `~/.local/share/EliteAIBridge/logs/runtime_setup.log`.
