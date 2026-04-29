@echo off
title Nanobot Omega — Gemini-Powered AI Agent
echo.
echo  ═══════════════════════════════════════════════════════
echo  ║           NANOBOT OMEGA — FUSION ACTIVE              ║
echo  ║  Limiteur global Gemini ^ Self-evolving ^ God Mode    ║
echo  ═══════════════════════════════════════════════════════
echo.
echo  [1] CLI Mode (interactive)
echo  [2] Gateway Mode (Telegram + API)  
echo  [3] Orchestrator Status
echo  [4] Omega Core Evolution (manual)
echo  [5] Quick Test
echo.

set /p choice="  Choix: "

if "%choice%"=="1" (
    echo.
    echo  Lancement CLI...
    python "C:\AI\nanobot-omega\nanobot_omega_launcher.py"
)
if "%choice%"=="2" (
    echo.
    echo  Lancement Gateway (Telegram + API)...
    python "C:\AI\nanobot-omega\nanobot_omega_launcher.py" --gateway
)
if "%choice%"=="3" (
    echo.
    python "C:\AI\nanobot-omega\nanobot_omega_launcher.py" --status
    echo.
    pause
)
if "%choice%"=="4" (
    echo.
    echo  Execution du cycle Omega Core...
    python "C:\AI\nanobot-omega\OMEGA_CORE.py" evolve
    echo.
    pause
)
if "%choice%"=="5" (
    echo.
    set /p prompt="  Prompt: "
    python "C:\AI\nanobot-omega\nanobot_omega_launcher.py" --test "%prompt%"
    echo.
    pause
)
