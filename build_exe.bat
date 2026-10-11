@echo off
rem Build a one-file Windows executable: dist\AutoTyper.exe
pyinstaller build_exe.spec --noconfirm
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)
echo Build succeeded: dist\AutoTyper.exe
