# PyInstaller spec: one-file Windows executable for Auto Typer.
# Build with: pyinstaller build_exe.spec
import sys
from pathlib import Path

sys.path.insert(0, SPECPATH)  # so the spec can import the package it builds
from auto_typer.background import write_icon  # noqa: E402

icon = write_icon(Path(SPECPATH) / "build" / "AutoTyper.ico")  # same icon as the window and tray

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="AutoTyper",
    debug=False,
    strip=False,
    # UPX-packed one-file exes are a common antivirus false positive, and this
    # app injects keystrokes, so it gets looked at closely. Leave it unpacked.
    upx=False,
    console=False,  # GUI app
    icon=str(icon),
)
