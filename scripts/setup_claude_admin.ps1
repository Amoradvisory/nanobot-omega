#requires -RunAsAdministrator
# Setup tout-en-un pour faire tourner Claude Code en admin sans UAC repete.
#
# 1) Verifie / installe Claude Code (Anthropic.ClaudeCode via winget)
# 2) Cree la tache planifiee "LaunchClaudeAdmin" avec privileges eleves
# 3) Cree un raccourci Bureau "Claude Admin.lnk" qui declenche la tache
#
# Une fois execute (1 seul UAC initial), double-clique sur le raccourci Bureau
# pour lancer Claude Code en admin SANS UAC additionnel.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host "=== Setup Claude Code admin ===" -ForegroundColor Cyan

# --- 1) Install / verify Claude Code via winget ----------------------------
Write-Host ""
Write-Host "[1/3] Verification / installation Claude Code..." -ForegroundColor Yellow

$claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
if ($claudeCmd) {
    Write-Host ("  Deja installe : " + $claudeCmd.Source) -ForegroundColor Green
} else {
    Write-Host "  Claude Code absent dans le PATH, installation via winget..."
    & winget install Anthropic.ClaudeCode --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host ("  winget exit=" + $LASTEXITCODE + " (peut etre normal si deja installe)") -ForegroundColor Yellow
    }
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
}

if (-not $claudeCmd) {
    Write-Host "  Recherche manuelle dans WinGet packages..." -ForegroundColor Yellow
    $found = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "claude.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        Write-Host ("  Trouve : " + $found.FullName) -ForegroundColor Green
        $claudeExe = $found.FullName
    } else {
        throw "Echec install Claude Code. Verifie : winget search Anthropic.ClaudeCode"
    }
} else {
    $claudeExe = $claudeCmd.Source
}
Write-Host ("  Claude Code : " + $claudeExe) -ForegroundColor Green

# --- 2) Wrapper deja sur disque, on verifie -----------------------------
$wrapperBat = "C:\AI\nanobot-omega\scripts\claude_admin_wrapper.cmd"
if (-not (Test-Path $wrapperBat)) {
    throw ("Wrapper manquant : " + $wrapperBat)
}
Write-Host ("  Wrapper : " + $wrapperBat) -ForegroundColor Green

# --- 3) Create scheduled task ------------------------------------------------
Write-Host ""
Write-Host "[2/3] Creation tache planifiee LaunchClaudeAdmin..." -ForegroundColor Yellow

$taskName = "LaunchClaudeAdmin"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument ('/c "' + $wrapperBat + '"')
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Description "Lance Claude Code en mode admin sans UAC. Trigger via schtasks /Run /TN LaunchClaudeAdmin." | Out-Null
Write-Host ("  Tache " + $taskName + " creee (RunLevel Highest)") -ForegroundColor Green

# --- 4) Create Desktop shortcut ----------------------------------------------
Write-Host ""
Write-Host "[3/3] Creation raccourci Bureau..." -ForegroundColor Yellow

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Claude Admin.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "C:\Windows\System32\schtasks.exe"
$shortcut.Arguments = ("/Run /TN " + $taskName)
$shortcut.WorkingDirectory = $env:USERPROFILE
$shortcut.WindowStyle = 7
$shortcut.IconLocation = ($claudeExe + ",0")
$shortcut.Description = "Claude Code en mode admin (sans UAC repete)"
$shortcut.Save()
Write-Host ("  Raccourci : " + $shortcutPath) -ForegroundColor Green

# --- Resume ----------------------------------------------------------------
Write-Host ""
Write-Host "=== INSTALLATION TERMINEE ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pour lancer Claude en admin :"
Write-Host "  - Double-clic sur 'Claude Admin' (Bureau)"
Write-Host "  - OU : schtasks /Run /TN LaunchClaudeAdmin"
Write-Host ""
Write-Host "Aucun UAC ne sera demande (la tache porte les privileges deja)."
Write-Host ""
Get-ScheduledTask -TaskName $taskName | Format-Table TaskName, State -AutoSize
Write-Host ""
Write-Host "Tu peux fermer cette fenetre."
Start-Sleep -Seconds 3
