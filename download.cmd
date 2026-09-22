@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  goto setup
)
".venv\Scripts\python.exe" -c "import douyin_local, yt_dlp, playwright, imageio_ffmpeg" >nul 2>&1
if errorlevel 1 goto setup
goto run
:setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1"
if errorlevel 1 goto finish
:run
".venv\Scripts\python.exe" -X utf8 -m douyin_local
:finish
echo.
pause
