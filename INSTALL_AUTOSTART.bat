@echo off
chcp 65001 >nul
title INSTALLATION DEMARRAGE AUTOMATIQUE NANOBOT

echo.
echo   ================================================================
echo        INSTALLATION DU DEMARRAGE AUTOMATIQUE
echo   ================================================================
echo.
echo   Ce script va configurer ton PC pour que Nanobot
echo   demarre AUTOMATIQUEMENT a chaque allumage.
echo.
echo   Methode : Planificateur de taches Windows (Task Scheduler)
echo.
echo   Appuie sur une touche pour installer...
pause >nul

echo.

REM ---------------------------------------------------------------
REM  1. Creer la tache planifiee principale
REM ---------------------------------------------------------------
echo   [1/3] Creation de la tache planifiee "Nanobot Omega Startup"...

schtasks /create ^
    /tn "Nanobot Omega Startup" ^
    /tr "cmd /c \"C:\AI\nanobot-omega\MASTER_STARTUP.bat\"" ^
    /sc onlogon ^
    /rl highest ^
    /f

if %errorlevel% equ 0 (
    echo         [OK] Tache "Nanobot Omega Startup" creee
) else (
    echo         [!!] Erreur — essayer en Administrateur ^(clic droit ^> Executer en admin^)
)

REM ---------------------------------------------------------------
REM  2. Creer une tache de surveillance (relance si crash)
REM ---------------------------------------------------------------
echo   [2/3] Creation du watchdog (relance toutes les 30 min)...

schtasks /create ^
    /tn "Nanobot Omega Watchdog" ^
    /tr "powershell -ExecutionPolicy Bypass -WindowStyle Hidden -Command \"& 'C:\AI\nanobot-omega\watchdog_check.ps1'\"" ^
    /sc minute ^
    /mo 30 ^
    /rl highest ^
    /f

if %errorlevel% equ 0 (
    echo         [OK] Tache "Nanobot Omega Watchdog" creee
) else (
    echo         [!!] Erreur watchdog — non critique
)

REM ---------------------------------------------------------------
REM  3. Nettoyer l'ancien autostart (Startup folder)
REM ---------------------------------------------------------------
echo   [3/3] Nettoyage ancien demarrage (dossier Startup)...

set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

if exist "%STARTUP%\OmegaAutostart.lnk" (
    del "%STARTUP%\OmegaAutostart.lnk"
    echo         [OK] Ancien OmegaAutostart.lnk supprime
) else (
    echo         [--] Pas d'ancien fichier a supprimer
)

if exist "%STARTUP%\Nanobot Telegram Gateway.vbs" (
    del "%STARTUP%\Nanobot Telegram Gateway.vbs"
    echo         [OK] Ancien VBS supprime
) else (
    echo         [--] Pas d'ancien VBS
)

echo.
echo   ================================================================
echo        INSTALLATION TERMINEE
echo   ================================================================
echo.
echo        [OK] Tache principale : "Nanobot Omega Startup"
echo            → Se lance automatiquement a chaque connexion
echo            → Lance : Sentinel + FIRE + Telegram + Watchtower + Brain
echo.
echo        [OK] Watchdog : "Nanobot Omega Watchdog"
echo            → Verifie toutes les 30 min que tout tourne
echo            → Relance automatiquement ce qui a crash
echo.
echo   Pour DESINSTALLER :
echo        schtasks /delete /tn "Nanobot Omega Startup" /f
echo        schtasks /delete /tn "Nanobot Omega Watchdog" /f
echo.
echo   Pour TESTER maintenant :
echo        Double-clique sur MASTER_STARTUP.bat
echo.
pause
