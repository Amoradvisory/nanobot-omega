$ErrorActionPreference = "Stop"

$nanobotExe = "C:\Users\user\.local\bin\nanobot.exe"
$pythonExe = "C:\Users\user\AppData\Roaming\uv\tools\nanobot-ai\Scripts\python.exe"
$configPath = "C:\AI\nanobot-omega\config_omega.json"
$startupContextScript = "C:\AI\nanobot-omega\scripts\build_startup_context.py"
$logDir = "C:\AI\nanobot-omega\logs"
$stateDir = "C:\AI\nanobot-omega\state"
$outLog = Join-Path $logDir "telegram-gateway.log"
$errLog = Join-Path $logDir "telegram-gateway.err.log"
$controlLog = Join-Path $logDir "telegram-gateway-control.log"
$lockPath = Join-Path $stateDir "gateway.lock"

if (-not (Test-Path $nanobotExe)) {
    throw "Nanobot introuvable: $nanobotExe"
}

if (-not (Test-Path $pythonExe)) {
    throw "Python Nanobot introuvable: $pythonExe"
}

if (-not (Test-Path $configPath)) {
    throw "Config Omega introuvable: $configPath"
}

$configObj = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$gatewayPort = [int]($configObj.gateway.port)
if ($gatewayPort -lt 1 -or $gatewayPort -gt 65535) {
    $gatewayPort = 18790
}

New-Item -ItemType Directory -Path $logDir -Force | Out-Null
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null

function Write-GatewayControlLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $controlLog -Value "$stamp $Message"
}

function Test-GatewayPortListening {
    param([int]$Port)
    try {
        return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    } catch {
        return $false
    }
}

function Get-NanobotGatewayProcesses {
    param([string]$ConfigPathEscaped)
    return @(Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -and
            $_.CommandLine -like "*nanobot.exe gateway*" -and
            $_.CommandLine -like "*config_omega.json*"
        })
}

function Get-ProcessTreeIds {
    param([int]$RootId)
    $all = @(Get-CimInstance Win32_Process)
    $ids = [System.Collections.Generic.HashSet[int]]::new()
    [void]$ids.Add($RootId)
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($p in $all) {
            $pidValue = [int]$p.ProcessId
            $parentId = [int]$p.ParentProcessId
            if ($ids.Contains($parentId) -and -not $ids.Contains($pidValue)) {
                [void]$ids.Add($pidValue)
                $changed = $true
            }
        }
    }
    return @($ids)
}

function Stop-ProcessTreeByRoot {
    param([int]$RootId)
    if ($RootId -le 0) { return }
    $ids = @(Get-ProcessTreeIds -RootId $RootId) | Sort-Object -Descending
    foreach ($id in $ids) {
        try {
            cmd /c "taskkill /PID $id /T /F" | Out-Null
            Write-GatewayControlLog "taskkill PID $id"
        } catch {
            try { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue } catch { }
        }
    }
}

function Test-ProcessAlive {
    param([int]$ProcessId)
    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Get-GatewayLock {
    if (-not (Test-Path -LiteralPath $lockPath)) { return $null }
    try {
        return Get-Content -LiteralPath $lockPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
        return $null
    }
}

function Write-GatewayLock {
    param([int]$ProcessId)
    $payload = [ordered]@{
        pid = $ProcessId
        timestamp = (Get-Date).ToUniversalTime().ToString("o")
        config = $configPath
    }
    $payload | ConvertTo-Json -Compress | Set-Content -LiteralPath $lockPath -Encoding UTF8
    Write-GatewayControlLog "gateway.lock written for PID $ProcessId"
}

function Invoke-TelegramWebhookReset {
    # Retry avec backoff exponentiel pour resister au DNS pas-encore-pret au boot Windows.
    # Sequence : try-immediat, +5s, +10s, +20s, +40s, +60s (total ~135s sur 6 essais).
    # Necessaire car au reboot, api.telegram.org peut prendre plusieurs dizaines de
    # secondes a etre resoluble apres l'autostart Nanobot par Task Scheduler.
    $token = [string]($configObj.channels.telegram.token)
    if ([string]::IsNullOrWhiteSpace($token)) {
        Write-GatewayControlLog "Telegram webhook reset skipped: token absent dans config."
        return
    }
    $base = "https://api.telegram.org/bot$token"

    $delays = @(0, 5, 10, 20, 40, 60)
    $totalAttempts = $delays.Count

    for ($i = 0; $i -lt $totalAttempts; $i++) {
        if ($delays[$i] -gt 0) {
            Start-Sleep -Seconds $delays[$i]
        }
        try {
            # Pre-check DNS : echoue tres vite si pas resolu, evite timeout HTTPS
            $null = [System.Net.Dns]::GetHostAddresses("api.telegram.org")
            # Reset webhook
            Invoke-RestMethod -Method Post -Uri "$base/setWebhook" -Body @{ url = "" } -TimeoutSec 15 | Out-Null
            Invoke-RestMethod -Method Post -Uri "$base/deleteWebhook" -Body @{ drop_pending_updates = "false" } -TimeoutSec 15 | Out-Null
            if ($i -gt 0) {
                Write-GatewayControlLog "Telegram webhook reset completed (apres $($i + 1) tentatives)."
            } else {
                Write-GatewayControlLog "Telegram webhook reset completed."
            }
            return
        } catch {
            $err = $_.Exception.Message
            $remaining = $totalAttempts - $i - 1
            if ($remaining -gt 0) {
                $nextDelay = $delays[$i + 1]
                Write-GatewayControlLog "Telegram webhook reset try $($i + 1)/$totalAttempts failed: $err. Retry dans $($nextDelay)s."
            } else {
                Write-GatewayControlLog "Telegram webhook reset FAILED apres $totalAttempts tentatives: $err"
            }
        }
    }
}

function Get-NanobotGatewayRootProcesses {
    param([string]$ConfigPathEscaped)
    $all = @(Get-NanobotGatewayProcesses -ConfigPathEscaped $ConfigPathEscaped)
    if ($all.Count -eq 0) { return @() }
    $matchIds = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($p in $all) { [void]$matchIds.Add([int]$p.ProcessId) }
    # Nanobot lance un worker avec la meme ligne de commande : ne compter que les racines
    # (parent pas un autre PID gateway identique).
    return @($all | Where-Object { -not $matchIds.Contains([int]$_.ParentProcessId) })
}

function Stop-DuplicateNanobotGatewayRoots {
    param([string]$ConfigPathEscaped)

    $all = @(Get-NanobotGatewayProcesses -ConfigPathEscaped $ConfigPathEscaped)
    if ($all.Count -eq 0) { return }

    $allIds = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($p in $all) { [void]$allIds.Add([int]$p.ProcessId) }
    $roots = @($all | Where-Object { -not $allIds.Contains([int]$_.ParentProcessId) } | Sort-Object ProcessId)
    if ($roots.Count -le 1) { return }

    $keepRoot = [int]$roots[0].ProcessId
    $killIds = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($root in $roots | Select-Object -Skip 1) {
        [void]$killIds.Add([int]$root.ProcessId)
    }

    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($p in $all) {
            $processId = [int]$p.ProcessId
            if ($processId -eq $keepRoot -or $killIds.Contains($processId)) { continue }
            if ($killIds.Contains([int]$p.ParentProcessId)) {
                [void]$killIds.Add($processId)
                $changed = $true
            }
        }
    }

    foreach ($processId in $killIds) {
        try { Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue } catch { }
    }
}

function Stop-AllNanobotGatewayProcesses {
    param([string]$ConfigPathEscaped)

    $all = @(Get-NanobotGatewayProcesses -ConfigPathEscaped $ConfigPathEscaped)
    foreach ($p in $all) {
        try { Stop-Process -Id ([int]$p.ProcessId) -Force -ErrorAction SilentlyContinue } catch { }
    }
}

$configEscaped = [regex]::Escape($configPath)

# Mutex: le superviseur appelle ce script toutes les 20 s ; un second lancement
# manuel peut coïncider — sans verrou, deux Start-Process passent la détection WMI.
$mutexName = "Local\NanobotOmegaTelegramGateway"
$mutex = $null
$acquired = $false
try {
    $mutex = New-Object System.Threading.Mutex($false, $mutexName)
    $acquired = $mutex.WaitOne(120000)
    if (-not $acquired) {
        throw "Impossible d'obtenir le verrou demarrage gateway ($mutexName) dans les delais."
    }

    $lock = Get-GatewayLock
    if ($null -ne $lock -and $lock.pid -and (Test-ProcessAlive -ProcessId ([int]$lock.pid))) {
        Write-GatewayControlLog "Existing gateway lock alive, PID $($lock.pid)."
        exit 0
    }
    if ($null -ne $lock -and $lock.pid) {
        Write-GatewayControlLog "Removing stale gateway lock for PID $($lock.pid)."
        Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
    }

    $gatewayProcesses = Get-NanobotGatewayRootProcesses -ConfigPathEscaped $configEscaped
    if ($gatewayProcesses.Count -gt 1) {
        Stop-AllNanobotGatewayProcesses -ConfigPathEscaped $configEscaped
        Start-Sleep -Seconds 5
        $gatewayProcesses = @()
    }

    if ($gatewayProcesses.Count -gt 0) {
        Write-GatewayLock -ProcessId ([int]$gatewayProcesses[0].ProcessId)
        exit 0
    }

    if (Test-GatewayPortListening -Port $gatewayPort) {
        exit 0
    }

    # Backend local par defaut: Ollama repond meme si Gemini est en cooldown.
    # Gemini reste disponible comme fallback quand Ollama local est indisponible.
    if ([string]::IsNullOrWhiteSpace($env:NANOBOT_BACKEND)) {
        $env:NANOBOT_BACKEND = "ollama"
    }
    if ([string]::IsNullOrWhiteSpace($env:NANOBOT_FALLBACK)) {
        $env:NANOBOT_FALLBACK = "1"
    }
    Write-GatewayControlLog "Backend actif: $env:NANOBOT_BACKEND, fallback: $env:NANOBOT_FALLBACK"

    if (Test-Path -LiteralPath $startupContextScript) {
        try {
            & python $startupContextScript --quiet | Out-Null
        } catch {
            $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            Add-Content -Path $errLog -Value "$stamp startup-context error: $($_.Exception.Message)"
        }
    }

    Invoke-TelegramWebhookReset

    $gatewayProcess = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @($nanobotExe, "gateway", "--config", $configPath) `
        -WindowStyle Hidden `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -PassThru

    if ($gatewayProcess -and $gatewayProcess.Id) {
        Write-GatewayLock -ProcessId ([int]$gatewayProcess.Id)
    }

    # Laisser WMI voir le processus avant de liberer le mutex (sinon un 2e lancement
    # superviseur + manuel demarre encore un gateway).
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 400
        if (Test-GatewayPortListening -Port $gatewayPort) { break }
        $seen = Get-NanobotGatewayRootProcesses -ConfigPathEscaped $configEscaped
        if ($seen.Count -gt 0) { break }
    }
}
finally {
    if ($null -ne $mutex) {
        if ($acquired) {
            try { $mutex.ReleaseMutex() } catch { }
        }
        try { $mutex.Dispose() } catch { }
    }
}
