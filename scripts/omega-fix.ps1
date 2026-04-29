<#
.SYNOPSIS
    omega-fix.ps1 — Self-Healing Engine pour Nanobot-Omega

.DESCRIPTION
    Auto-diagnostic et reparation du systeme en une seule commande.
    Identifie et corrige : Chrome orphelins, lock files, processus fantomes,
    tmp satures, cache bloque, etat corrompu.

.USAGE
    # Diagnostic seul (aucune modification)
    powershell -ExecutionPolicy Bypass -File C:\AI\nanobot-omega\scripts\omega-fix.ps1 -DiagOnly

    # Reparation automatique (defaut)
    powershell -ExecutionPolicy Bypass -File C:\AI\nanobot-omega\scripts\omega-fix.ps1

    # Reparation agressive (tout tuer, tout nettoyer)
    powershell -ExecutionPolicy Bypass -File C:\AI\nanobot-omega\scripts\omega-fix.ps1 -Aggressive

    # Appel rapide depuis exec() Gemini
    exec("powershell -ExecutionPolicy Bypass -File C:\\AI\\nanobot-omega\\scripts\\omega-fix.ps1")

.NOTES
    Auteur: Claude (Anthropic) pour Commandant Supreme
    Version: 1.0.0
    Date: 2026-04-16
#>

param(
    [switch]$DiagOnly,      # Diagnostic sans action
    [switch]$Aggressive,    # Mode agressif : kill tout, purge tout
    [switch]$Silent         # Pas de sortie console (pour cron/watchdog)
)

$ErrorActionPreference = "SilentlyContinue"

# === CONFIG ===
$CHROME_PROFILE = "C:\AI\nanobot-omega\shared-browser\chrome-profile"
$LIGHT_HOMES = "C:\AI\nanobot-omega\gemini-light-homes"
$STATE_DIR = "C:\AI\nanobot-omega\state"
$SHARED_STATE = "C:\AI\nanobot-omega\shared_state.json"

# Fichiers de verrouillage Chrome connus
$LOCK_FILES = @(
    "$CHROME_PROFILE\SingletonLock",
    "$CHROME_PROFILE\SingletonSocket",
    "$CHROME_PROFILE\SingletonCookie",
    "$CHROME_PROFILE\Default\LOCK",
    "$CHROME_PROFILE\Default\lockfile",
    "$CHROME_PROFILE\lockfile"
)

# Resultats
$report = @{
    timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    issues_found = 0
    issues_fixed = 0
    actions = [System.Collections.ArrayList]::new()
    warnings = [System.Collections.ArrayList]::new()
}

function Log($msg, $level = "INFO") {
    if (-not $Silent) {
        $prefix = switch ($level) {
            "OK"    { "[OK]  " }
            "FIX"   { "[FIX] " }
            "WARN"  { "[!!]  " }
            "DIAG"  { "[>>]  " }
            default { "[--]  " }
        }
        Write-Host "$prefix $msg"
    }
}

function Add-Issue($msg) {
    $report.issues_found++
    [void]$report.warnings.Add($msg)
    Log $msg "WARN"
}

function Add-Fix($msg) {
    $report.issues_fixed++
    [void]$report.actions.Add($msg)
    Log $msg "FIX"
}

# =============================================
# 1. CHROME ORPHELINS
# =============================================
function Check-ChromeOrphelins {
    Log "--- Chrome : processus orphelins ---" "DIAG"

    $chromeProcs = Get-Process -Name chrome -ErrorAction SilentlyContinue
    if (-not $chromeProcs) {
        Log "Aucun processus Chrome actif" "OK"
        return
    }

    $count = $chromeProcs.Count
    Log "Chrome: $count processus detectes" "INFO"

    # Verifier si le port CDP 9222 repond (Chrome fonctionnel)
    $cdpAlive = $false
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", 9222)
        $cdpAlive = $tcp.Connected
        $tcp.Close()
    } catch {}

    if ($cdpAlive) {
        Log "CDP port 9222 repond : Chrome fonctionnel" "OK"

        # Verifier s'il y a des processus Chrome qui ne font rien (CPU=0 depuis longtemps)
        $zombies = $chromeProcs | Where-Object {
            $_.Responding -eq $false
        }
        if ($zombies) {
            Add-Issue "$($zombies.Count) processus Chrome non-responsive"
            if (-not $DiagOnly) {
                foreach ($z in $zombies) {
                    Stop-Process -Id $z.Id -Force
                    Add-Fix "Chrome zombie PID $($z.Id) termine"
                }
            }
        }
    } else {
        # Chrome tourne mais CDP ne repond pas = orphelins probables
        Add-Issue "Chrome actif ($count proc) mais CDP 9222 ne repond pas = orphelins"

        if (-not $DiagOnly) {
            # Identifier les Chrome lies a notre profil
            foreach ($proc in $chromeProcs) {
                try {
                    $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)").CommandLine
                    if ($cmdline -and $cmdline -match "nanobot-omega") {
                        Stop-Process -Id $proc.Id -Force
                        Add-Fix "Chrome orphelin PID $($proc.Id) termine (profil nanobot)"
                    }
                } catch {}
            }

            # Si mode agressif : tuer TOUS les chrome.exe
            if ($Aggressive) {
                Stop-Process -Name chrome -Force -ErrorAction SilentlyContinue
                Add-Fix "Mode agressif : tous les chrome.exe termines"
            }
        }
    }
}

# =============================================
# 2. FICHIERS DE VERROUILLAGE CHROME
# =============================================
function Check-LockFiles {
    Log "--- Chrome : fichiers de verrouillage ---" "DIAG"

    $locksFound = 0
    foreach ($lockFile in $LOCK_FILES) {
        if (Test-Path $lockFile) {
            $locksFound++
            Add-Issue "Lock file present : $lockFile"

            if (-not $DiagOnly) {
                # Verifier si Chrome tourne avant de supprimer
                $chromeRunning = Get-Process -Name chrome -ErrorAction SilentlyContinue
                if (-not $chromeRunning) {
                    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
                    Add-Fix "Lock file supprime : $lockFile"
                } else {
                    Log "Chrome actif, lock file conserve (normal)" "INFO"
                }
            }
        }
    }

    if ($locksFound -eq 0) {
        Log "Aucun fichier de verrouillage residuel" "OK"
    }
}

# =============================================
# 3. PROCESSUS FANTOMES (pwsh, cmd)
# =============================================
function Check-GhostProcesses {
    Log "--- Processus fantomes (pwsh, cmd) ---" "DIAG"

    $ghosts = @()

    # pwsh.exe fantomes (plus de 2h d'age, pas de fenetre)
    $pwshProcs = Get-Process -Name pwsh -ErrorAction SilentlyContinue | Where-Object {
        $_.MainWindowHandle -eq 0 -and
        (New-TimeSpan -Start $_.StartTime -End (Get-Date)).TotalHours -gt 2
    }
    if ($pwshProcs) { $ghosts += $pwshProcs }

    # cmd.exe fantomes (plus de 2h, pas de fenetre)
    $cmdProcs = Get-Process -Name cmd -ErrorAction SilentlyContinue | Where-Object {
        $_.MainWindowHandle -eq 0 -and
        (New-TimeSpan -Start $_.StartTime -End (Get-Date)).TotalHours -gt 2
    }
    if ($cmdProcs) { $ghosts += $cmdProcs }

    # conhost fantomes lies a des sessions mortes
    $conhostProcs = Get-Process -Name conhost -ErrorAction SilentlyContinue | Where-Object {
        (New-TimeSpan -Start $_.StartTime -End (Get-Date)).TotalHours -gt 4
    }

    if ($ghosts.Count -eq 0) {
        Log "Aucun processus fantome detecte" "OK"
        return
    }

    Add-Issue "$($ghosts.Count) processus fantome(s) detecte(s)"

    if (-not $DiagOnly) {
        foreach ($ghost in $ghosts) {
            $age = [math]::Round((New-TimeSpan -Start $ghost.StartTime -End (Get-Date)).TotalHours, 1)
            Stop-Process -Id $ghost.Id -Force -ErrorAction SilentlyContinue
            Add-Fix "$($ghost.ProcessName) PID $($ghost.Id) termine (age: ${age}h)"
        }
    }

    # Mode agressif : aussi les conhost vieux
    if ($Aggressive -and $conhostProcs -and -not $DiagOnly) {
        foreach ($ch in $conhostProcs) {
            Stop-Process -Id $ch.Id -Force -ErrorAction SilentlyContinue
        }
        Add-Fix "Mode agressif : $($conhostProcs.Count) conhost anciens termines"
    }
}

# =============================================
# 4. REPERTOIRES TMP GEMINI
# =============================================
function Check-GeminiTmp {
    Log "--- Repertoires .gemini/tmp ---" "DIAG"

    $totalSize = 0
    $totalFiles = 0
    $cleanedDirs = 0

    foreach ($letter in 'A','B','C','D','E','F','G','H','I','J') {
        $tmpDir = "$LIGHT_HOMES\gemini_$letter\.gemini\tmp"
        if (Test-Path $tmpDir) {
            $files = Get-ChildItem $tmpDir -Recurse -File -ErrorAction SilentlyContinue
            $dirSize = ($files | Measure-Object -Property Length -Sum).Sum
            $dirSizeMB = [math]::Round($dirSize / 1MB, 1)
            $fileCount = $files.Count

            $totalSize += $dirSize
            $totalFiles += $fileCount

            # Seuil : 50 MB ou 500 fichiers = saturation
            if ($dirSizeMB -gt 50 -or $fileCount -gt 500) {
                Add-Issue "gemini_$letter/tmp sature : ${dirSizeMB} MB, $fileCount fichiers"

                if (-not $DiagOnly) {
                    # Supprimer les fichiers de plus de 24h
                    $cutoff = (Get-Date).AddHours(-24)
                    $oldFiles = $files | Where-Object { $_.LastWriteTime -lt $cutoff }
                    foreach ($f in $oldFiles) {
                        Remove-Item $f.FullName -Force -ErrorAction SilentlyContinue
                    }
                    if ($oldFiles) {
                        Add-Fix "gemini_$letter/tmp : $($oldFiles.Count) fichiers anciens supprimes"
                    }
                    $cleanedDirs++
                }
            }
        }
    }

    $totalSizeMB = [math]::Round($totalSize / 1MB, 1)
    if ($totalFiles -eq 0) {
        Log "Aucun fichier temporaire dans les light-homes" "OK"
    } else {
        Log "Total tmp : ${totalSizeMB} MB, $totalFiles fichiers dans $cleanedDirs repertoire(s)" "INFO"
    }

    # Aussi verifier workspace/tmp
    $workspaceTmp = "C:\AI\nanobot-omega\workspace\tmp"
    if (Test-Path $workspaceTmp) {
        $wsFiles = Get-ChildItem $workspaceTmp -Recurse -File -ErrorAction SilentlyContinue
        $wsSizeMB = [math]::Round(($wsFiles | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
        if ($wsSizeMB -gt 100) {
            Add-Issue "workspace/tmp sature : ${wsSizeMB} MB"
            if (-not $DiagOnly) {
                $cutoff = (Get-Date).AddHours(-48)
                $old = $wsFiles | Where-Object { $_.LastWriteTime -lt $cutoff }
                foreach ($f in $old) { Remove-Item $f.FullName -Force -ErrorAction SilentlyContinue }
                Add-Fix "workspace/tmp : $($old.Count) fichiers anciens supprimes"
            }
        }
    }
}

# =============================================
# 5. ETAT SYSTEME (shared_state.json)
# =============================================
function Check-SharedState {
    Log "--- Etat systeme (shared_state.json) ---" "DIAG"

    if (-not (Test-Path $SHARED_STATE)) {
        Add-Issue "shared_state.json absent!"
        return
    }

    try {
        $stateRaw = Get-Content $SHARED_STATE -Raw -Encoding utf8
        $state = $stateRaw | ConvertFrom-Json
        $now = [double](Get-Date -UFormat %s)

        $blacklisted = 0
        $highErrors = 0
        $staleBlacklists = @()
        $instanceCount = 0

        $state.instances.PSObject.Properties | ForEach-Object {
            $instanceCount++
            $instName = $_.Name
            $bl = [double]$_.Value.blacklisted_until
            $ce = [int]$_.Value.consecutive_errors

            if ($bl -gt $now) {
                $blacklisted++
                $remainingH = [math]::Round(($bl - $now) / 3600, 1)
                if ($remainingH -gt 24) {
                    $staleBlacklists += $instName
                }
            }
            if ($ce -gt 10) { $highErrors++ }
        }

        $available = $instanceCount - $blacklisted
        Log "Instances: $available/10 disponibles, $blacklisted blacklistees" "INFO"

        if ($blacklisted -ge 8) {
            Add-Issue "CRITIQUE : $blacklisted/10 instances blacklistees!"
            if (-not $DiagOnly) {
                # Reset automatique si 8+ blacklistees
                foreach ($inst in $instances) {
                    $inst.Value.blacklisted_until = 0
                    $inst.Value.consecutive_errors = 0
                    $inst.Value.last_error_msg = ""
                }
                $state.timestamp = $now
                $state | ConvertTo-Json -Depth 10 | Set-Content $SHARED_STATE -Encoding utf8
                Add-Fix "Reset automatique : 10/10 instances debloquees"
            }
        } elseif ($staleBlacklists.Count -gt 0) {
            Add-Issue "Blacklists obsoletes (>24h) : $($staleBlacklists -join ', ')"
            if (-not $DiagOnly) {
                foreach ($inst in $instances) {
                    if ($staleBlacklists -contains $inst.Name) {
                        $inst.Value.blacklisted_until = 0
                        $inst.Value.consecutive_errors = 0
                    }
                }
                $state.timestamp = $now
                $state | ConvertTo-Json -Depth 10 | Set-Content $SHARED_STATE -Encoding utf8
                Add-Fix "Blacklists obsoletes resettees : $($staleBlacklists -join ', ')"
            }
        } else {
            Log "Etat instances sain" "OK"
        }

    } catch {
        Add-Issue "shared_state.json corrompu ou illisible : $_"
    }
}

# =============================================
# 6. LOGS ET STATE (rotation)
# =============================================
function Check-LogsRotation {
    Log "--- Logs et fichiers d'etat ---" "DIAG"

    $files = @(
        @{ Path = "$STATE_DIR\resilient.log"; MaxKB = 500 },
        @{ Path = "$STATE_DIR\state_history.jsonl"; MaxKB = 500 },
        @{ Path = "$STATE_DIR\loop_detector.json"; MaxKB = 50 }
    )

    foreach ($f in $files) {
        if (Test-Path $f.Path) {
            $sizeKB = [math]::Round((Get-Item $f.Path).Length / 1KB, 1)
            $name = Split-Path $f.Path -Leaf

            if ($sizeKB -gt $f.MaxKB) {
                Add-Issue "$name sature : ${sizeKB} KB (max $($f.MaxKB) KB)"
                if (-not $DiagOnly) {
                    $ts = Get-Date -Format "yyyyMMdd_HHmmss"
                    $backup = $f.Path -replace '(\.\w+)$', ".$ts`$1.bak"
                    Move-Item $f.Path $backup -Force
                    New-Item $f.Path -ItemType File -Force | Out-Null
                    Add-Fix "$name archive et reinitialise"
                }
            } else {
                Log "$name : ${sizeKB} KB (OK)" "OK"
            }
        }
    }
}

# =============================================
# 7. INTEGRITE PROFIL CHROME
# =============================================
function Check-ChromeProfileIntegrity {
    Log "--- Integrite profil Chrome ---" "DIAG"

    $prefsFile = "$CHROME_PROFILE\Default\Preferences"
    if (-not (Test-Path $prefsFile)) {
        Add-Issue "Chrome Preferences absent!"
        return
    }

    try {
        $prefs = Get-Content $prefsFile -Raw | ConvertFrom-Json

        # Verifier que nos settings de securite sont toujours en place
        $contentSettings = $prefs.profile.default_content_setting_values

        if ($contentSettings.notifications -ne 2) {
            Add-Issue "Notifications Chrome non bloquees (derive detectee)"
            if (-not $DiagOnly) {
                $prefs.profile.default_content_setting_values.notifications = 2
                $prefs | ConvertTo-Json -Depth 20 | Set-Content $prefsFile -Encoding utf8
                Add-Fix "Notifications re-bloquees"
            }
        }

        if ($contentSettings.popups -ne 2) {
            Add-Issue "Popups Chrome non bloques (derive detectee)"
            if (-not $DiagOnly) {
                $prefs.profile.default_content_setting_values.popups = 2
                $prefs | ConvertTo-Json -Depth 20 | Set-Content $prefsFile -Encoding utf8
                Add-Fix "Popups re-bloques"
            }
        }

        Log "Preferences Chrome integres" "OK"

    } catch {
        Add-Issue "Chrome Preferences corrompu : $_"
    }

    # Verifier que les extensions problematiques sont toujours desactivees
    $problematic = @(
        "amhmeenmapldpjdedekalnfifgnpfnkc",  # Superpower ChatGPT
        "hghepaogndoaijlgelomneagnjlhaled",  # Readio TTS
        "nmmicjeknamkfloonkhhcjmomieiodli"   # YouTube Summary
    )
    $extDir = "$CHROME_PROFILE\Default\Extensions"
    foreach ($extId in $problematic) {
        $active = "$extDir\$extId"
        $disabled = "$extDir\$extId.disabled"
        if ((Test-Path $active) -and -not (Test-Path $disabled)) {
            Add-Issue "Extension problematique reactivee : $extId"
            if (-not $DiagOnly) {
                Rename-Item $active "$extId.disabled" -Force -ErrorAction SilentlyContinue
                Add-Fix "Extension $extId re-desactivee"
            }
        }
    }
}

# =============================================
# EXECUTION
# =============================================

if (-not $Silent) {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "  OMEGA-FIX : Self-Healing Engine v1.0"
    Write-Host "  $($report.timestamp)"
    if ($DiagOnly) { Write-Host "  MODE : Diagnostic seul (aucune modification)" }
    elseif ($Aggressive) { Write-Host "  MODE : Reparation AGRESSIVE" }
    else { Write-Host "  MODE : Reparation automatique" }
    Write-Host "============================================================"
    Write-Host ""
}

# Executer tous les checks
Check-ChromeOrphelins
Check-LockFiles
Check-GhostProcesses
Check-GeminiTmp
Check-SharedState
Check-LogsRotation
Check-ChromeProfileIntegrity

# Resume final
if (-not $Silent) {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "  RESUME"
    Write-Host "============================================================"
    Write-Host "  Problemes detectes : $($report.issues_found)"
    Write-Host "  Problemes corriges : $($report.issues_fixed)"

    if ($report.issues_found -eq 0) {
        Write-Host ""
        Write-Host "  SYSTEME SAIN. Aucune intervention necessaire."
    } elseif ($DiagOnly -and $report.issues_found -gt 0) {
        Write-Host ""
        Write-Host "  Relancer sans -DiagOnly pour corriger automatiquement."
    }
    Write-Host ""
}

# Code de sortie
if ($report.issues_found -eq 0) { exit 0 }
elseif ($report.issues_fixed -eq $report.issues_found) { exit 0 }
else { exit 1 }
