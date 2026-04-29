$ErrorActionPreference = "Stop"

$scriptPath = "C:\AI\nanobot-omega\Run-NanobotOmegaSupervisor.ps1"
$gatewayStarter = "C:\AI\nanobot-omega\Start-NanobotTelegramGateway.ps1"
$staleTelegramStopper = "C:\AI\nanobot-omega\scripts\Stop-StaleTelegramNanobot.ps1"
$statusScript = "C:\AI\nanobot-omega\omega_status.py"
$startupContextScript = "C:\AI\nanobot-omega\scripts\build_startup_context.py"
$logDir = "C:\AI\nanobot-omega\logs"
$stateDir = "C:\AI\nanobot-omega\state"
$supervisorLog = Join-Path $logDir "omega-supervisor.log"
$supervisorErr = Join-Path $logDir "omega-supervisor.err.log"
$gatewayLock = Join-Path $stateDir "gateway.lock"
$forceGatewayRestart = Join-Path $stateDir "force_gateway_restart"

New-Item -ItemType Directory -Path $logDir -Force | Out-Null
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null

$otherSupervisors = Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and
    $_.CommandLine -and
    $_.CommandLine -match [regex]::Escape($scriptPath) -and
    $_.CommandLine -notmatch "Start-Process"
}
if ($otherSupervisors) {
    exit 0
}

function Write-SupervisorLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $supervisorLog -Value "$stamp $Message"
}

function Get-NanobotGatewayRootCount {
    if (Test-Path -LiteralPath $gatewayLock) {
        try {
            $lock = Get-Content -LiteralPath $gatewayLock -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($lock.pid -and (Get-Process -Id ([int]$lock.pid) -ErrorAction SilentlyContinue)) {
                return 1
            }
            Remove-Item -LiteralPath $gatewayLock -Force -ErrorAction SilentlyContinue
        } catch {
            Remove-Item -LiteralPath $gatewayLock -Force -ErrorAction SilentlyContinue
        }
    }

    $all = @(Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -and
            $_.CommandLine -like "*nanobot.exe gateway --config*" -and
            $_.CommandLine -like "*config_omega.json*" -and
            $_.CommandLine -notmatch "Get-CimInstance|Where-Object|Select-Object"
        })
    if ($all.Count -eq 0) { return 0 }

    $ids = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($p in $all) { [void]$ids.Add([int]$p.ProcessId) }
    $roots = @($all | Where-Object { -not $ids.Contains([int]$_.ParentProcessId) })
    return $roots.Count
}

function Stop-GatewayByPort {
    try {
        $owners = @(Get-NetTCPConnection -LocalPort 18790 -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)
        $all = @(Get-CimInstance Win32_Process)
        $targets = [System.Collections.Generic.HashSet[int]]::new()
        foreach ($owner in $owners) {
            if ([int]$owner -le 0) { continue }
            [void]$targets.Add([int]$owner)
            $proc = $all | Where-Object { [int]$_.ProcessId -eq [int]$owner } | Select-Object -First 1
            if ($proc -and $proc.ParentProcessId) {
                $parent = $all | Where-Object { [int]$_.ProcessId -eq [int]$proc.ParentProcessId } | Select-Object -First 1
                if ($parent -and $parent.Name -match "^(python|powershell|cmd)(\.exe)?$") {
                    [void]$targets.Add([int]$parent.ProcessId)
                }
            }
        }
        foreach ($processId in @($targets) | Sort-Object -Descending) {
            try {
                cmd /c "taskkill /PID $processId /T /F" | Out-Null
                Write-SupervisorLog "Forced gateway PID tree stopped: $processId"
            } catch {
                $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                Add-Content -Path $supervisorErr -Value "$stamp force-gateway-stop error PID ${processId}: $($_.Exception.Message)"
            }
        }
        Remove-Item -LiteralPath $gatewayLock -Force -ErrorAction SilentlyContinue
    } catch {
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $supervisorErr -Value "$stamp force-gateway-stop error: $($_.Exception.Message)"
    }
}

Write-SupervisorLog "Supervisor started."
Write-SupervisorLog "Backend actif: $env:NANOBOT_BACKEND, fallback: $env:NANOBOT_FALLBACK"

if (Test-Path -LiteralPath $startupContextScript) {
    try {
        & python $startupContextScript --quiet | Out-Null
        Write-SupervisorLog "Startup capability context refreshed."
    } catch {
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $supervisorErr -Value "$stamp startup-context error: $($_.Exception.Message)"
    }
}

if (Test-Path -LiteralPath $staleTelegramStopper) {
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $staleTelegramStopper | Out-Null
        Write-SupervisorLog "Stale Telegram poller cleanup executed."
    } catch {
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $supervisorErr -Value "$stamp stale-cleanup error: $($_.Exception.Message)"
    }
}

$lastStaleCleanup = Get-Date

while ($true) {
    try {
        if (Test-Path -LiteralPath $staleTelegramStopper -and ((Get-Date) - $lastStaleCleanup).TotalSeconds -ge 60) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $staleTelegramStopper | Out-Null
            $lastStaleCleanup = Get-Date
        }
    } catch {
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $supervisorErr -Value "$stamp periodic-stale-cleanup error: $($_.Exception.Message)"
    }

    try {
        if (Test-Path -LiteralPath $forceGatewayRestart) {
            Remove-Item -LiteralPath $forceGatewayRestart -Force -ErrorAction SilentlyContinue
            Write-SupervisorLog "Forced gateway restart requested by marker."
            Stop-GatewayByPort
            Start-Sleep -Seconds 5
        }

        $gatewayRootCount = Get-NanobotGatewayRootCount
        if ($gatewayRootCount -ne 1) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $gatewayStarter | Out-Null
        }
    } catch {
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $supervisorErr -Value "$stamp gateway-start error: $($_.Exception.Message)"
    }

    try {
        & python $statusScript --write | Out-Null
    } catch {
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $supervisorErr -Value "$stamp status-write error: $($_.Exception.Message)"
    }

    Start-Sleep -Seconds 20
}
