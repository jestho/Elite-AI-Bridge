# Changelog

## Unreleased

### Linux (experimental)
- The Bridge can be started on Linux with `RUN_CURRENT_SOURCE.sh` when Elite Dangerous runs
  under Steam Proton. The journal, Status.json, bindings and DisplaySettings.xml are found
  inside the Proton prefix (every Steam library is checked), Bridge data lives in
  `~/.local/share/EliteAIBridge`, and `ELITE_JOURNAL_DIR`, `ELITE_BINDINGS_DIR`,
  `ELITE_PROTON_PREFIX` and `ELITE_AI_BRIDGE_DATA_DIR` override the lookup. See LINUX.md.
- Sound effects and the Supertonic voice play through sounddevice on any OS; they were
  refused outside Windows before.
- The verified OpenAI key is kept between runs on Linux in an owner-only file in the Bridge
  data folder (Windows keeps using the user environment variable).
- Cockpit actions on Linux press keys through a uinput virtual keyboard
  (`common/eab_linux_input.py`, no extra Python packages) and check the active window with
  xdotool or xprop/wmctrl, failing closed when they cannot. `RUN_CURRENT_SOURCE.sh --input`
  reports the setup. Station automation gates on the key sender's availability instead of
  the OS, and the game process is detected with pgrep.
- Global hotkeys, keyboard push to talk and the Windows voice fallback remain Windows-only.

### Changed
- `Elite AI Bridge/common/eab_platform.py` is the one place that resolves Elite's folders
  and the Bridge data folder; Windows paths are unchanged.

## 2.0.0 - 2026-10-10

A complete redesign of Elite AI Bridge.

### New
- Retro command deck interface: Flight Deck, Combat, Trade, Navigation, Colonization,
  Commander and Setup, rebuilt from scratch.
- Setup wizard: Elite, your keys, controls, sound, which screen the Bridge and the overlay
  go on, and an optional AI add-on run with the OpenAI key typed or pasted into a normal box.
- Guided tours: every page has a short spoken tour on its ? key.
- Bounty Hunting: finds Resource Extraction Sites by danger level, with search range and
  site distance controls.
- Commander odd stats, cargo and loadout views in the Flight Deck event log.
- In-game overlay: off until you turn it on, goes on the screen you pick, and steps aside
  while the Bridge window is in front on the same screen.
- Ship voice says plainly when Elite has no keyboard key for something you asked for, and
  where to set one.
- Bug reporting from Setup > Status: a support file, then GitHub or email.

### Install and safety
- The installer shows a checklist with live progress while it prepares the runtime.
- The Bridge opens fullscreen.
- Shortcuts run the runtime's own Python (signed by the Python Software Foundation);
  there is no VBScript or custom launcher.
- Every runtime package is pinned to an exact, tested version.
- Full SIL Open Font License text included with the bundled fonts.

## 1.0.1 - 2026-09-30
Maintenance and startup release: Supertonic voice backend restored, boot sequence added,
cleaner shutdown and documentation updates.

## 1.0.0 - 2026-09-27
First public release.
