@echo off
chcp 65001 >nul
title NANOBOT OMEGA — Demarrage Complet 24/7

echo.
echo   ================================================================
echo        NANOBOT OMEGA — DEMARRAGE SYSTEME COMPLET
echo   ================================================================
echo        Date : %date% %time%
echo   ================================================================
echo.

REM ---------------------------------------------------------------
REM  ETAPE 0 : Attente de stabilisation post-login
REM ---------------------------------------------------------------
echo   [0/5] Attente stabilisation systeme (10s)...
timeout /t 10 /nobreak >nul

REM ---------------------------------------------------------------
REM  ETAPE 1 : Nettoyage des processus zombies (Sentinel)
REM ---------------------------------------------------------------
echo   [1/5] Nettoyage processus zombies (Sentinel)...
python "C:\AI\nanobot-omega\OMEGA_SENTINEL.py" 2>nul
if %errorlevel% equ 0 (
    echo         [OK] Sentinel termine
) else (
    echo         [!!] Sentinel en erreur — on continue
)

REM ---------------------------------------------------------------
REM  ETAPE 2 : Lancement du Superviseur FIRE (Chrome, Terminal, IDE)
REM ---------------------------------------------------------------
echo   [2/5] Lancement FIRE Supervisor (port 7000)...
start "FIRE SUPERVISOR" /min cmd /c "cd /d C:\Users\user\Desktop\FIRE && set PYTHONIOENCODING=utf-8 && python scripts/supervisor.py serve"
timeout /t 3 /nobreak >nul
echo         [OK] FIRE Supervisor lance (http://127.0.0.1:7000)

REM ---------------------------------------------------------------
REM  ETAPE 3 : Lancement du Gateway Telegram Nanobot
REM ---------------------------------------------------------------
echo   [3/5] Lancement Gateway Telegram...
start "OMEGA TELEGRAM" /min powershell -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\AI\nanobot-omega\Start-NanobotTelegramGateway.ps1"
timeout /t 3 /nobreak >nul
echo         [OK] Telegram Gateway lance (port 18790)

REM ---------------------------------------------------------------
REM  ETAPE 4 : Lancement de la Watchtower (veille proactive)
REM ---------------------------------------------------------------
echo   [4/5] Lancement Watchtower (veille 24/7)...
start "OMEGA WATCHTOWER" /min python "C:\AI\nanobot-omega\OMEGA_WATCHTOWER.py"
timeout /t 2 /nobreak >nul
echo         [OK] Watchtower active (cycle toutes les 2h)

REM ---------------------------------------------------------------
REM  ETAPE 5 : Lancement du Brain Nanobot (agent principal)
REM ---------------------------------------------------------------
echo   [5/5] Lancement Nanobot Brain (gateway mode)...
start "OMEGA BRAIN" /min python "C:\AI\nanobot-omega\nanobot_omega_launcher.py" --gateway
timeout /t 3 /nobreak >nul
echo         [OK] Nanobot Brain lance

REM ---------------------------------------------------------------
REM  RESUME
REM ---------------------------------------------------------------
echo.
echo   ================================================================
echo        SYSTEME OPERATIONNEL — AUTONOMIE 24/7 ACTIVE
echo   ================================================================
echo.
echo        [OK] Sentinel         — Nettoyage fait
echo        [OK] FIRE Supervisor  — http://127.0.0.1:7000
echo        [OK] Telegram Gateway — port 18790
echo        [OK] Watchtower       — Veille proactive
echo        [OK] Nanobot Brain    — Agent principal
echo.
echo        Pour verifier : ouvre http://127.0.0.1:7000
echo        Pour Telegram : envoie un message a ton bot
echo.
echo   ================================================================
echo   Cette fenetre va se fermer dans 15 secondes.
echo   ================================================================
timeout /t 15 >nul
