# PyInstaller spec: one-file Windows executable for Auto Typer.
# Build with: pyinstaller build_exe.spec
import sys

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
    upx=True,
    console=False,  # GUI app
    icon=None,
)
