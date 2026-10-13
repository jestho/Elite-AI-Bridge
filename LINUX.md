# Elite AI Bridge on Linux (Elite Dangerous under Proton)

Elite AI Bridge is a Windows application. This page describes the experimental native
Linux run of the same source, for pilots who play Elite Dangerous through Steam Proton.
It is a work in progress: the dashboard, data, voice and AI parts run; anything that
presses keys in the cockpit does not yet. See "What does not work yet" below before you
spend time on it.

## What works
- The full interface: Flight Deck, Combat, Trade, Navigation, Colonization, Commander,
  Setup wizard and page tours.
- Live game state from the journal and Status.json inside the Proton prefix.
- Trade, bounty hunting, colonization and route searches (EDDN cache, EDData, Ardent
  Insight, INTRA, EDSM).
- The ship voice (Supertonic, local) and sound effects, through PortAudio.
- The optional OpenAI co-pilot, including push to talk on a HOTAS or controller button.
- The OpenAI key typed into the setup wizard is kept between runs.

## What does not work yet
- **Cockpit actions.** Dock, Launch, Clear and Jump, route plotting, station services,
  combat macros, Dynamic PIPs, auto chaff and the trade loop all send keystrokes to the
  game through the Windows `SendInput` API. On Linux they report that no active Elite
  bindings profile is available, or that key sending is Windows-only. A Linux key sender
  (uinput or xdotool) is the next piece of work.
- **Global hotkeys and keyboard push to talk.** These use Windows `RegisterHotKey`. Map
  push to talk to a HOTAS or controller button instead.
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
- **Logs:** `~/.local/share/EliteAIBridge/qml_backend.log` and
  `~/.local/share/EliteAIBridge/logs/runtime_setup.log`.
