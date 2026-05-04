@echo off
REM Lance Codex CLI en heritant des privileges admin de la tache planifiee.
REM Utilise Windows Terminal (wt.exe) s'il est dispo, sinon cmd direct.
cd /d "%USERPROFILE%"

REM Cherche codex.exe dans le PATH d'abord
where codex.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "CODEX_EXE=codex.exe"
    goto :LAUNCH
)

REM Sinon cherche dans WinGet packages
for /f "delims=" %%I in ('dir /b /s "%LOCALAPPDATA%\Microsoft\WinGet\Packages\OpenAI.Codex*\codex.exe" 2^>nul') do (
    set "CODEX_EXE=%%I"
    goto :LAUNCH
)

echo Codex CLI introuvable. Lance d'abord setup_codex_admin.ps1.
pause
exit /b 1

:LAUNCH
where wt.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    wt.exe -d "%USERPROFILE%" "%CODEX_EXE%"
) else (
    "%CODEX_EXE%"
    pause
)
