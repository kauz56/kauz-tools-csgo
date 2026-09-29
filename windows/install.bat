@echo off
rem kauz-tools-csgo installer/updater: rerun after unzipping a new version
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
pause
