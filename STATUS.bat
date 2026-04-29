@echo off
chcp 65001 >nul
title NANOBOT OMEGA — Status Systeme
color 0A

echo.
echo   ================================================================
echo        NANOBOT OMEGA — STATUS SYSTEME
echo        %date% %time%
echo   ================================================================
echo.

echo   Verification en cours...
echo.

REM --- FIRE Supervisor ---
powershell -NoProfile -Command "try { $null = Invoke-WebRequest -Uri 'http://127.0.0.1:7000/api/health' -TimeoutSec 3 -UseBasicParsing; Write-Host '  [OK] FIRE Supervisor    — actif (port 7000)' } catch { Write-Host '  [!!] FIRE Supervisor    — INACTIF' }"

REM --- Telegram Gateway ---
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*nanobot.exe gateway*' -and $_.CommandLine -like '*config_omega.json*' }; if ($p) { Write-Host '  [OK] Telegram Gateway   — actif (polling)' } else { Write-Host '  [!!] Telegram Gateway   — INACTIF' }"

REM --- Chrome CDP ---
powershell -NoProfile -Command "try { $tcp = New-Object System.Net.Sockets.TcpClient; $tcp.Connect('127.0.0.1',9222); $tcp.Close(); Write-Host '  [OK] Chrome Agent       — actif (port 9222)' } catch { Write-Host '  [!!] Chrome Agent       — INACTIF' }"

REM --- Watchtower ---
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*OMEGA_WATCHTOWER*' }; if ($p) { Write-Host '  [OK] Watchtower         — actif' } else { Write-Host '  [!!] Watchtower         — INACTIF' }"

REM --- Nanobot Brain ---
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { ($_.CommandLine -like '*nanobot.exe gateway*' -and $_.CommandLine -like '*config_omega.json*') -or $_.CommandLine -like '*nanobot_omega_launcher*--gateway*' }; if ($p) { Write-Host '  [OK] Nanobot Brain      — actif' } else { Write-Host '  [!!] Nanobot Brain      — INACTIF' }"

echo.
echo   --- Taches Planifiees ---

schtasks /query /tn "Nanobot Omega Startup" >nul 2>nul
if %errorlevel% equ 0 (
    echo   [OK] Demarrage auto     — installe
) else (
    echo   [!!] Demarrage auto     — PAS INSTALLE
)

schtasks /query /tn "Nanobot Omega Watchdog" >nul 2>nul
if %errorlevel% equ 0 (
    echo   [OK] Watchdog 30min     — installe
) else (
    echo   [!!] Watchdog 30min     — PAS INSTALLE
)

REM --- Limiteur Gemini ---
echo.
echo   --- Limiteur Gemini ---
python "C:\AI\nanobot-omega\omega_status.py"

REM --- Parametres energie ---
echo.
echo   --- Energie ---
powershell -NoProfile -Command "$lid = powercfg /query SCHEME_CURRENT 4f971e89-eebd-4455-a8de-9e59040e7347 5ca83367-6e45-459f-a27b-476b1d01c936 | Select-String 'Current AC'; if ($lid -match '0x00000000') { Write-Host '  [OK] Fermer le capot   — ne fait rien (OK)' } else { Write-Host '  [!!] Fermer le capot   — ATTENTION: met en veille!' }"
powershell -NoProfile -Command "$sleep = powercfg /query SCHEME_CURRENT 238c9fa8-0aad-41ed-83f4-97be242c8f20 29f6c1db-86da-48c5-9fdb-f2b67b1f44da | Select-String 'Current AC'; if ($sleep -match '0x00000000') { Write-Host '  [OK] Mise en veille    — desactivee (OK)' } else { Write-Host '  [!!] Mise en veille    — ATTENTION: active!' }"

echo.
echo   ================================================================
echo.
echo   Appuie sur une touche pour fermer cette fenetre...
echo.
pause >nul
