<#
.SYNOPSIS
    preflight.ps1 — Sanitize le systeme avant une operation lourde.

.DESCRIPTION
    Execute omega-fix.ps1 en mode silencieux (nettoyage Chrome orphelins,
    lock files, processus fantomes), verifie la RAM disponible, puis lance
    la commande passee en argument. Soft-fail : si omega-fix echoue, la
    commande est executee quand meme.

.USAGE
    preflight.ps1 -- npm run build
    preflight.ps1 -MinRamMB 3500 -- firebase deploy
    preflight.ps1 -Skip -- npm install   # bypass (urgence)

.NOTES
    Appele automatiquement par les wrappers npm/yarn/pnpm/firebase/vite
    definis dans le profil PowerShell.
#>

[CmdletBinding(PositionalBinding=$false)]
param(
    [int]$MinRamMB = 3000,
    [switch]$Skip,
    [switch]$ShowDetail,
    [Parameter(Position=0, ValueFromRemainingArguments=$true)]
    [string[]]$Command
)

$ErrorActionPreference = "Continue"
$OmegaFix = "C:\AI\nanobot-omega\scripts\omega-fix.ps1"
$LogDir = "C:\AI\nanobot-omega\logs"
$LogFile = Join-Path $LogDir "preflight.log"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Write-PreflightLog([string]$msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "[$ts] $msg"
    if ($ShowDetail) { Write-Host "[preflight] $msg" -ForegroundColor DarkCyan }
}

# --- Validation argument ---
if (-not $Command -or $Command.Count -eq 0) {
    Write-Host "preflight: aucune commande fournie. Usage: preflight.ps1 -- <commande>" -ForegroundColor Red
    exit 2
}

$cmdLine = ($Command -join ' ')
Write-PreflightLog "START: $cmdLine"

# --- Bypass si demande ---
if ($Skip) {
    Write-PreflightLog "SKIP demande - execution directe"
    & $Command[0] @($Command | Select-Object -Skip 1)
    exit $LASTEXITCODE
}

# --- Etape 1 : omega-fix silent ---
if (Test-Path $OmegaFix) {
    Write-Host "[preflight] Nettoyage systeme (omega-fix)..." -ForegroundColor DarkCyan
    try {
        & powershell -ExecutionPolicy Bypass -NoProfile -File $OmegaFix -Silent 2>&1 | Out-Null
        Write-PreflightLog "omega-fix OK"
    } catch {
        Write-PreflightLog "omega-fix ERROR: $_"
        Write-Host "[preflight] omega-fix a echoue, on continue quand meme." -ForegroundColor Yellow
    }
} else {
    Write-PreflightLog "omega-fix introuvable a $OmegaFix"
}

# --- Etape 2 : verification RAM ---
try {
    $os = Get-CimInstance Win32_OperatingSystem
    $freeMB = [math]::Round($os.FreePhysicalMemory / 1024)
    $totalMB = [math]::Round($os.TotalVisibleMemorySize / 1024)
    Write-PreflightLog "RAM libre: ${freeMB}MB / ${totalMB}MB (seuil ${MinRamMB}MB)"

    if ($freeMB -lt $MinRamMB) {
        Write-Host "[preflight] RAM faible (${freeMB}MB libre < ${MinRamMB}MB requis). Nouvelle passe agressive..." -ForegroundColor Yellow
        if (Test-Path $OmegaFix) {
            & powershell -ExecutionPolicy Bypass -NoProfile -File $OmegaFix -Aggressive -Silent 2>&1 | Out-Null
        }
        Start-Sleep -Seconds 2
        $os2 = Get-CimInstance Win32_OperatingSystem
        $freeMB2 = [math]::Round($os2.FreePhysicalMemory / 1024)
        Write-PreflightLog "RAM apres aggressive: ${freeMB2}MB"

        if ($freeMB2 -lt $MinRamMB) {
            Write-Host "[preflight] RAM toujours insuffisante (${freeMB2}MB). Commande lancee quand meme avec NODE_OPTIONS augmente." -ForegroundColor Yellow
            $env:NODE_OPTIONS = "--max-old-space-size=4096"
        }
    }
} catch {
    Write-PreflightLog "RAM check ERROR: $_"
}

# --- Etape 3 : injection NODE_OPTIONS si build Node detecte ---
$isNodeBuild = $cmdLine -match '\b(npm|yarn|pnpm|vite|next|vercel|netlify|firebase)\b'
if ($isNodeBuild -and -not $env:NODE_OPTIONS) {
    $env:NODE_OPTIONS = "--max-old-space-size=4096"
    Write-PreflightLog "NODE_OPTIONS injecte: $env:NODE_OPTIONS"
}

# --- Etape 4 : execution de la commande ---
Write-Host "[preflight] -> $cmdLine" -ForegroundColor DarkGreen
Write-PreflightLog "EXEC: $cmdLine"

$exe = $Command[0]
$rest = @()
if ($Command.Count -gt 1) { $rest = $Command[1..($Command.Count - 1)] }

& $exe @rest
$code = $LASTEXITCODE

Write-PreflightLog "END: exit=$code"
exit $code
