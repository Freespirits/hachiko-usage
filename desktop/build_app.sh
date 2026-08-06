#!/usr/bin/env bash
# Build Devil-Usage.app (the 3D desktop pet) for macOS.
# Run from the desktop/ folder: ./build_app.sh
set -euo pipefail
cd "$(dirname "$0")"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "This builds the macOS .app — run it on a Mac. (Windows: build_exe.bat)" >&2
  exit 1
fi

python3 -m pip install --upgrade PySide6 pyinstaller

# hojek.icns from the committed PNG iconset. iconutil ships with macOS, so this
# needs no extra dependency — and Pillow cannot write .icns off a Mac anyway.
if [[ ! -f hojek.icns ]]; then
  echo "==> hojek.icns from ../assets/icon.iconset"
  iconutil -c icns ../assets/icon.iconset -o hojek.icns
fi

rm -rf build "dist/Devil-Usage.app" dist/DevilUsage
pyinstaller --noconfirm DevilUsage-mac.spec

# Apple Silicon refuses to run unsigned Mach-O binaries, so ad-hoc sign the
# bundle and strip the quarantine flag PyInstaller's downloads may carry.
echo "==> ad-hoc signing"
codesign --force --deep --sign - "dist/Devil-Usage.app"
xattr -cr "dist/Devil-Usage.app"

echo
echo "Done: dist/Devil-Usage.app"
echo
echo "First launch: right-click the app -> Open (it is unsigned, so Gatekeeper"
echo "asks once). Launch the .app itself, not dist/DevilUsage/DevilUsage —"
echo "QtWebEngine needs the bundle layout to find its helper process."
