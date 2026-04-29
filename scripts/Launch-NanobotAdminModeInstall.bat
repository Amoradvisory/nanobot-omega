@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""C:\AI\nanobot-omega\scripts\Install-NanobotAdminMode.ps1""'"
endlocal
