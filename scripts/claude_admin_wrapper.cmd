@echo off
REM Lance Claude Code en heritant des privileges admin de la tache planifiee.
REM Utilise Windows Terminal (wt.exe) s'il est dispo, sinon cmd direct.
cd /d "%USERPROFILE%"

REM Cherche claude.exe dans le PATH d'abord
where claude.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "CLAUDE_EXE=claude.exe"
    goto :LAUNCH
)

REM Sinon cherche dans WinGet packages
for /f "delims=" %%I in ('dir /b /s "%LOCALAPPDATA%\Microsoft\WinGet\Packages\Anthropic.ClaudeCode*\claude.exe" 2^>nul') do (
    set "CLAUDE_EXE=%%I"
    goto :LAUNCH
)

echo Claude Code introuvable. Lance d'abord setup_claude_admin.ps1.
pause
exit /b 1

:LAUNCH
where wt.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    wt.exe -d "%USERPROFILE%" "%CLAUDE_EXE%"
) else (
    "%CLAUDE_EXE%"
    pause
)
