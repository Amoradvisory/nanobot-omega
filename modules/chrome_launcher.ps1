# ============================================================================
# CHROME LAUNCHER - Gestionnaire d'Instance Unique Ultra-Rapide
# ============================================================================
# Usage:
#   .\chrome_launcher.ps1                    -> Lance ou reutilise Chrome
#   .\chrome_launcher.ps1 -Url "https://..."  -> Ouvre un onglet dans Chrome existant
#   .\chrome_launcher.ps1 -Status             -> Etat de la session Chrome
#   .\chrome_launcher.ps1 -Kill               -> Fermer proprement Chrome
#   .\chrome_launcher.ps1 -Reset              -> Redemarrage propre
# ============================================================================

param(
    [string]$Url = "",
    [switch]$Status,
    [switch]$Kill,
    [switch]$Reset,
    [int]$DebugPort = 9222,
    [string]$ProfilePath = "C:\AI\nanobot-omega\shared-browser\chrome-profile"
)

$ErrorActionPreference = "SilentlyContinue"

# --- Fonctions utilitaires ---

function Get-ChromePath {
    $paths = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Test-ChromeRunning {
    $procs = Get-Process -Name "chrome" -ErrorAction SilentlyContinue
    return ($null -ne $procs -and $procs.Count -gt 0)
}

function Test-DebugPortOpen {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", $DebugPort)
        $tcp.Close()
        return $true
    } catch {
        return $false
    }
}

function Get-ChromeTabs {
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$DebugPort/json" -TimeoutSec 3
        return $response
    } catch {
        return @()
    }
}

function Open-TabInExisting {
    param([string]$TargetUrl)
    try {
        # Methode 1 : CDP newTab
        $body = @{ url = $TargetUrl } | ConvertTo-Json
        Invoke-RestMethod -Uri "http://127.0.0.1:$DebugPort/json/new?$TargetUrl" -TimeoutSec 5
        return $true
    } catch {
        # Methode 2 : start chrome avec URL (Chrome existant capture comme nouvel onglet)
        $chromePath = Get-ChromePath
        if ($chromePath) {
            Start-Process $chromePath -ArgumentList $TargetUrl
            return $true
        }
        return $false
    }
}

function Start-ChromeFresh {
    $chromePath = Get-ChromePath
    if (-not $chromePath) {
        Write-Host "[ERREUR] Chrome introuvable sur ce systeme." -ForegroundColor Red
        return $false
    }

    # Creer le profil si inexistant
    if (-not (Test-Path $ProfilePath)) {
        New-Item -ItemType Directory -Path $ProfilePath -Force | Out-Null
    }

    $args = @(
        "--user-data-dir=$ProfilePath",
        "--remote-debugging-port=$DebugPort",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-hang-monitor",
        "--enable-features=NetworkService",
        "--restore-last-session"
    )

    if ($Url) { $args += $Url }

    Start-Process $chromePath -ArgumentList ($args -join " ")

    # Attente active du port CDP (max 8s)
    $maxWait = 16
    for ($i = 0; $i -lt $maxWait; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-DebugPortOpen) {
            Write-Host "[OK] Chrome lance en $(($i+1)*500)ms - CDP actif sur port $DebugPort" -ForegroundColor Green
            return $true
        }
    }

    Write-Host "[WARN] Chrome lance mais CDP pas encore actif apres 8s" -ForegroundColor Yellow
    return $true
}

function Stop-ChromeClean {
    $tabs = Get-ChromeTabs
    if ($tabs.Count -gt 0) {
        Write-Host "[INFO] Fermeture de $($tabs.Count) onglet(s)..." -ForegroundColor Cyan
    }

    # Demande polie via CDP
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$DebugPort/json/close" -TimeoutSec 3 | Out-Null
    } catch {}

    # Fallback : taskkill propre
    Stop-Process -Name "chrome" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500

    if (-not (Test-ChromeRunning)) {
        Write-Host "[OK] Chrome ferme proprement." -ForegroundColor Green
    } else {
        # Force kill
        taskkill /F /IM chrome.exe 2>$null | Out-Null
        Write-Host "[OK] Chrome force-kill effectue." -ForegroundColor Yellow
    }
}

function Show-Status {
    $chromeRunning = Test-ChromeRunning
    $cdpActive = Test-DebugPortOpen
    $tabs = @()
    if ($cdpActive) { $tabs = Get-ChromeTabs }

    Write-Host ""
    Write-Host "  === CHROME SESSION STATUS ===" -ForegroundColor Cyan
    Write-Host "  Chrome running  : $(if($chromeRunning){'OUI'}else{'NON'})" -ForegroundColor $(if($chromeRunning){'Green'}else{'Red'})
    Write-Host "  CDP port $DebugPort   : $(if($cdpActive){'ACTIF'}else{'INACTIF'})" -ForegroundColor $(if($cdpActive){'Green'}else{'Red'})
    Write-Host "  Profile         : $ProfilePath"
    Write-Host "  Onglets ouverts : $($tabs.Count)"

    if ($tabs.Count -gt 0) {
        Write-Host ""
        $i = 1
        foreach ($tab in $tabs) {
            if ($tab.type -eq "page") {
                $title = if ($tab.title.Length -gt 60) { $tab.title.Substring(0,57) + "..." } else { $tab.title }
                Write-Host "    [$i] $title" -ForegroundColor White
                $i++
            }
        }
    }
    Write-Host ""
}

# --- Execution principale ---

if ($Status) {
    Show-Status
    exit 0
}

if ($Kill) {
    Stop-ChromeClean
    exit 0
}

if ($Reset) {
    Write-Host "[INFO] Reset Chrome..." -ForegroundColor Yellow
    Stop-ChromeClean
    Start-Sleep -Seconds 1

    # Nettoyer les fichiers de lock corrompus
    $lockFiles = @(
        "$ProfilePath\SingletonLock",
        "$ProfilePath\SingletonSocket",
        "$ProfilePath\SingletonCookie"
    )
    foreach ($f in $lockFiles) {
        if (Test-Path $f) { Remove-Item $f -Force }
    }

    Start-ChromeFresh
    exit 0
}

# Mode par defaut : lancer ou reutiliser
$cdpActive = Test-DebugPortOpen

if ($cdpActive) {
    # Chrome est deja actif avec CDP
    if ($Url) {
        Write-Host "[REUSE] Chrome actif - ouverture onglet..." -ForegroundColor Cyan
        $ok = Open-TabInExisting -TargetUrl $Url
        if ($ok) {
            Write-Host "[OK] Onglet ouvert : $Url" -ForegroundColor Green
        } else {
            Write-Host "[ERREUR] Impossible d'ouvrir l'onglet" -ForegroundColor Red
        }
    } else {
        Write-Host "[REUSE] Chrome deja actif sur CDP port $DebugPort" -ForegroundColor Green
        $tabs = Get-ChromeTabs
        Write-Host "  Onglets : $($tabs.Count)" -ForegroundColor Cyan
    }
} else {
    # Chrome pas actif ou pas en mode debug -> lancer
    if (Test-ChromeRunning) {
        Write-Host "[WARN] Chrome tourne mais sans CDP. Redemarrage avec profil agent..." -ForegroundColor Yellow
        Stop-ChromeClean
        Start-Sleep -Seconds 1
    }
    Start-ChromeFresh
}

