@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create .venv and install requirements-native.txt first. See docs/native-desktop.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "%~dp0native_play.py" %*
if errorlevel 1 pause
