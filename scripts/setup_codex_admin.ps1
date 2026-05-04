#requires -RunAsAdministrator
# Setup tout-en-un pour faire tourner Codex CLI en admin sans UAC repete.
#
# 1) Installe Codex CLI (Win32, via winget) si pas deja present
# 2) Cree la tache planifiee "LaunchCodexAdmin" avec privileges eleves
# 3) Cree un raccourci Bureau "Codex Admin.lnk" qui declenche la tache
#
# Une fois execute (1 seul UAC initial), double-clique sur le raccourci Bureau
# pour lancer Codex CLI en admin SANS UAC additionnel.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host "=== Setup Codex CLI admin ===" -ForegroundColor Cyan

# --- 1) Install Codex CLI via winget ----------------------------------------
Write-Host ""
Write-Host "[1/3] Verification / installation Codex CLI..." -ForegroundColor Yellow

$codexCmd = Get-Command codex -ErrorAction SilentlyContinue
if ($codexCmd) {
    Write-Host ("  Deja installe : " + $codexCmd.Source) -ForegroundColor Green
} else {
    Write-Host "  Codex CLI absent, installation via winget (peut prendre 1-2 min)..."
    & winget install OpenAI.Codex --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host ("  winget exit=" + $LASTEXITCODE + " (peut etre normal si deja installe)") -ForegroundColor Yellow
    }
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $codexCmd = Get-Command codex -ErrorAction SilentlyContinue
}

if (-not $codexCmd) {
    Write-Host "  Recherche manuelle dans WinGet packages..." -ForegroundColor Yellow
    $found = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "codex.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        Write-Host ("  Trouve : " + $found.FullName) -ForegroundColor Green
        $codexExe = $found.FullName
    } else {
        throw "Echec install Codex CLI. Verifie : winget search OpenAI.Codex"
    }
} else {
    $codexExe = $codexCmd.Source
}
Write-Host ("  Codex CLI : " + $codexExe) -ForegroundColor Green

# --- 2) Wrapper deja sur disque, on verifie -----------------------------
$wrapperBat = "C:\AI\nanobot-omega\scripts\codex_admin_wrapper.cmd"
if (-not (Test-Path $wrapperBat)) {
    throw ("Wrapper manquant : " + $wrapperBat)
}
Write-Host ("  Wrapper : " + $wrapperBat) -ForegroundColor Green

# --- 3) Create scheduled task ------------------------------------------------
Write-Host ""
Write-Host "[2/3] Creation tache planifiee LaunchCodexAdmin..." -ForegroundColor Yellow

$taskName = "LaunchCodexAdmin"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument ('/c "' + $wrapperBat + '"')
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Description "Lance Codex CLI en mode admin sans UAC. Trigger via schtasks /Run /TN LaunchCodexAdmin." | Out-Null
Write-Host ("  Tache " + $taskName + " creee (RunLevel Highest)") -ForegroundColor Green

# --- 4) Create Desktop shortcut ----------------------------------------------
Write-Host ""
Write-Host "[3/3] Creation raccourci Bureau..." -ForegroundColor Yellow

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Codex Admin.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "C:\Windows\System32\schtasks.exe"
$shortcut.Arguments = ("/Run /TN " + $taskName)
$shortcut.WorkingDirectory = $env:USERPROFILE
$shortcut.WindowStyle = 7
$shortcut.IconLocation = ($codexExe + ",0")
$shortcut.Description = "Codex CLI en mode admin (sans UAC repete)"
$shortcut.Save()
Write-Host ("  Raccourci : " + $shortcutPath) -ForegroundColor Green

# --- Resume ----------------------------------------------------------------
Write-Host ""
Write-Host "=== INSTALLATION TERMINEE ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pour lancer Codex en admin :"
Write-Host "  - Double-clic sur 'Codex Admin' (Bureau)"
Write-Host "  - OU : schtasks /Run /TN LaunchCodexAdmin"
Write-Host ""
Write-Host "Aucun UAC ne sera demande (la tache porte les privileges deja)."
Write-Host ""
Get-ScheduledTask -TaskName $taskName | Format-Table TaskName, State -AutoSize
Write-Host ""
Write-Host "Tu peux fermer cette fenetre."
Start-Sleep -Seconds 3
