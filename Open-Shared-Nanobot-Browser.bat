@echo off
setlocal

set "SHARED_PROFILE=C:\AI\nanobot-omega\shared-browser\chrome-profile"
if not exist "%SHARED_PROFILE%" mkdir "%SHARED_PROFILE%"

set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_EXE%" set "CHROME_EXE=C:\Users\user\AppData\Local\ms-playwright\chromium-1208\chrome-win64\chrome.exe"

set "TARGET_URL=%~1"
if "%TARGET_URL%"=="" set "TARGET_URL=https://www.google.fr"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$portOpen = [bool](Get-NetTCPConnection -LocalPort 9222 -State Listen -ErrorAction SilentlyContinue); " ^
  "if (-not $portOpen) { " ^
  "  Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'chrome.exe' -and $_.CommandLine -and $_.CommandLine -like '*C:\AI\nanobot-omega\shared-browser\chrome-profile*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; " ^
  "}"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$portOpen = [bool](Get-NetTCPConnection -LocalPort 9222 -State Listen -ErrorAction SilentlyContinue); " ^
  "if ($portOpen) { " ^
  "  Start-Process -FilePath '%CHROME_EXE%' -ArgumentList @('--user-data-dir=%SHARED_PROFILE%', '%TARGET_URL%'); " ^
  "} else { " ^
  "  Start-Process -FilePath '%CHROME_EXE%' -ArgumentList @('--user-data-dir=%SHARED_PROFILE%', '--remote-debugging-port=9222', '--remote-allow-origins=*', '--no-first-run', '--no-default-browser-check', '--disable-background-timer-throttling', '--restore-last-session', '%TARGET_URL%'); " ^
  "}"

exit /b 0
