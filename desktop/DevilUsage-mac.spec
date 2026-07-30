# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the macOS .app bundle.

Deliberately separate from DevilUsage.spec: build_exe.bat drives pyinstaller
with CLI arguments, which regenerates DevilUsage.spec and would clobber this.

Build with:  cd desktop && ./build_app.sh      (or: pyinstaller --noconfirm DevilUsage-mac.spec)

Must stay --onedir. QtWebEngine cannot run from a --onefile bundle on macOS:
the QtWebEngineProcess helper has to exist as a real file inside the bundle.
"""

from pathlib import Path

HERE = Path(SPECPATH)          # desktop/
ROOT = HERE.parent            # repo root

datas = [
    (str(ROOT / "desktop3d.html"), "."),
    (str(ROOT / "three.min.js"), "."),
    (str(ROOT / "GLTFLoader.js"), "."),
    (str(ROOT / "cute-hd.glb"), "."),
    (str(ROOT / "evil-hd.glb"), "."),
    (str(HERE / "hojek.ico"), "."),
    (str(ROOT / "assets" / "tray.png"), "."),
    (str(ROOT / "assets" / "tray@2x.png"), "."),
]

a = Analysis(
    [str(HERE / "hojek3d_desktop.pyw")],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DevilUsage",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX mangles Mach-O binaries and breaks code signing
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,    # native arch; universal2 needs a universal2 Python
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DevilUsage",
)
app = BUNDLE(
    coll,
    name="Devil-Usage.app",
    icon=str(HERE / "hojek.icns"),
    bundle_identifier="ai.freespirits.devilusage",
    info_plist={
        # menu-bar-only accessory app: no Dock icon, no app menu, no window list
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "CFBundleName": "Devil-Usage",
        "CFBundleDisplayName": "Devil-Usage",
        "CFBundleShortVersionString": "1.1.0",
        "CFBundleVersion": "1.1.0",
        "LSMinimumSystemVersion": "11.0",
    },
)
