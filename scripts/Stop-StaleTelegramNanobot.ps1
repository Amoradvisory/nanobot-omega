$ErrorActionPreference = "SilentlyContinue"

$logDir = "C:\AI\nanobot-omega\logs"
$stateDir = "C:\AI\nanobot-omega\state"
$logPath = Join-Path $logDir "stale-telegram-cleanup.log"
$lockPath = Join-Path $stateDir "gateway.lock"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

function Write-CleanupLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $logPath -Value "$stamp $Message"
}

function Add-ProcessTree {
    param(
        [int]$RootId,
        [array]$AllProcesses,
        [System.Collections.Generic.HashSet[int]]$TargetSet
    )

    if ($RootId -le 0) { return }
    [void]$TargetSet.Add($RootId)

    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($p in $AllProcesses) {
            $pidValue = [int]$p.ProcessId
            $parentId = [int]$p.ParentProcessId
            if ($TargetSet.Contains($parentId) -and -not $TargetSet.Contains($pidValue)) {
                [void]$TargetSet.Add($pidValue)
                $changed = $true
            }
        }
    }
}

$all = @(Get-CimInstance Win32_Process)
$toStop = [System.Collections.Generic.HashSet[int]]::new()
$keepIds = [System.Collections.Generic.HashSet[int]]::new()

if (Test-Path -LiteralPath $lockPath) {
    try {
        $lock = Get-Content -LiteralPath $lockPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($lock.pid -and (Get-Process -Id ([int]$lock.pid) -ErrorAction SilentlyContinue)) {
            Add-ProcessTree -RootId ([int]$lock.pid) -AllProcesses $all -TargetSet $keepIds
            Write-CleanupLog "Preserving locked gateway PID $($lock.pid)."
        }
    } catch {
    }
}

# Historical elevated Telegram pollers that can survive normal user restarts.
$knownStaleRoots = @(1840, 10904, 7884)
foreach ($rootId in $knownStaleRoots) {
    Add-ProcessTree -RootId $rootId -AllProcesses $all -TargetSet $toStop
}

# If several Nanobot Telegram gateways are alive, keep only the newest root.
$gatewayProcesses = @($all | Where-Object {
    $_.CommandLine -and
    $_.CommandLine -like "*nanobot.exe gateway --config*" -and
    $_.CommandLine -like "*config_omega.json*" -and
    $_.CommandLine -notmatch "Get-CimInstance|Where-Object|Select-Object"
})

if ($gatewayProcesses.Count -gt 0) {
    $gatewayIds = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($p in $gatewayProcesses) { [void]$gatewayIds.Add([int]$p.ProcessId) }

    $gatewayRoots = @($gatewayProcesses | Where-Object {
        -not $gatewayIds.Contains([int]$_.ParentProcessId)
    } | Sort-Object CreationDate -Descending)

    $keepRoot = $null
    if ($gatewayRoots.Count -gt 0) {
        $keepRoot = [int]$gatewayRoots[0].ProcessId
        Write-CleanupLog "Keeping newest gateway root PID $keepRoot."
    }

    foreach ($root in $gatewayRoots | Select-Object -Skip 1) {
        $rootId = [int]$root.ProcessId
        if ($keepIds.Contains($rootId)) { continue }
        Write-CleanupLog "Stopping duplicate gateway root PID $rootId."
        Add-ProcessTree -RootId $rootId -AllProcesses $all -TargetSet $toStop
    }
}

# Hidden/elevated Python pollers may have no command line. Detect only Telegram
# API connections owned by python processes and keep the lock-protected gateway.
$telegramOwners = @(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | Where-Object {
    $_.RemotePort -eq 443 -and (
        $_.RemoteAddress -like "149.154.*" -or
        $_.RemoteAddress -like "91.108.*" -or
        $_.RemoteAddress -like "2001:67c:4e8:*"
    )
} | Select-Object -ExpandProperty OwningProcess -Unique)

foreach ($owner in $telegramOwners) {
    $proc = $all | Where-Object { [int]$_.ProcessId -eq [int]$owner } | Select-Object -First 1
    if ($null -eq $proc -or $proc.Name -notmatch "python") { continue }
    if ($keepIds.Contains([int]$owner)) { continue }
    Write-CleanupLog "Stopping hidden Telegram python poller PID $owner."
    Add-ProcessTree -RootId ([int]$owner) -AllProcesses $all -TargetSet $toStop
}

$ids = @($toStop | Where-Object { -not $keepIds.Contains([int]$_) }) | Sort-Object -Descending
if ($ids.Count -eq 0) {
    Write-CleanupLog "No stale Telegram poller found."
    exit 0
}

Write-CleanupLog ("Stopping stale process tree: " + ($ids -join ", "))
foreach ($id in $ids) {
    try {
        Stop-Process -Id $id -Force
        Write-CleanupLog "Stopped PID $id."
    } catch {
        Write-CleanupLog "Could not stop PID ${id}: $($_.Exception.Message)"
    }
}

Start-Sleep -Seconds 2
