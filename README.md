# Hachiko-Usage

A loyal little desktop pet that watches your Claude usage. He is a plant-fox
hatched by the Codex hatch pipeline (originally named Hojek), reborn as
**Hachiko-Usage**: he waits faithfully on top of your taskbar with a thought
cloud showing your Claude Code session and weekly usage limits.

![Hachiko-Usage on the desktop](hachiko-usage.png)

**[⬇ Download Hachiko-Usage-Setup.exe](https://github.com/Freespirits/hachiko-usage/releases/latest)** —
one press and he's yours (Windows 10/11, per-user install, no admin needed).

He starts in **ghost mode** — 50% transparent, click-through (your mouse goes
straight through him), and tiny (half his old size) — so he never gets in the
way of real work.

## Controls

While click-through is on, the pet window ignores the mouse, so everything is
driven from his **system tray icon** (right-click it):

- states: wave, jump, fly, working, waiting, review, failed, idle
- `ghost 50%` — toggle the transparency
- `click-through` — toggle mouse pass-through (off = you can drag, click to
  wave, double-click to jump, right-click him directly)
- `size` — tiny (default), small, medium, large
- hide/show the usage cloud, quit

The tray tooltip also shows the current session/weekly percentages.

## Run from source

```
desktop\Start Hachiko-Usage.bat
```

(Uses the bundled venv: PySide6 + PyInstaller.)

## Build the one-press installer

```
cd desktop
venv\Scripts\pyinstaller.exe Hachiko-Usage.spec --noconfirm
ISCC.exe Hachiko-Usage.iss
```

This produces `desktop\installer\Hachiko-Usage-Setup.exe` — a one-press
installer: launching it immediately installs to
`%localappdata%\Programs\Hachiko-Usage` (no wizard pages, no admin rights)
and offers to let him out right away.

## Usage data

`desktop\hachiko_usage_desktop.pyw` polls
`https://api.anthropic.com/api/oauth/usage` with the local Claude Code OAuth
token from `~\.claude\.credentials.json`. Only the percentages are kept; the
token never leaves the request.

## Also in this repo

- `index.html` / `hojek-atlas.png` / `hojek.json` — the original web sprite
  version and the hatch-pipeline atlas he is drawn from
- `desktop3d.html`, `cute.glb`, `evil.glb`, `desktop/hojek3d_desktop.pyw` —
  the experimental 3D variant (still under the old name)
