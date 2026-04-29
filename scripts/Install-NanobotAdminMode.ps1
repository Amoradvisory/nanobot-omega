$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    Write-Error "This installer must run elevated. Re-launch it with Run as administrator."
    exit 740
}

$root = "C:\AI\nanobot-omega"
$scriptsDir = Join-Path $root "scripts"
$logDir = Join-Path $root "logs"
$backupRoot = Join-Path $root "backups"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $backupRoot "admin-mode-$stamp"
$statusPath = Join-Path $logDir "admin-mode-install-status.txt"
$supervisorScript = Join-Path $root "Run-NanobotOmegaSupervisor.ps1"
$taskName = "NanobotOmegaSupervisorAdmin"
$watchdogTaskName = "NanobotWatchdogAdmin"
$dashboardTaskName = "NanobotDashboardAdmin"
$indexTaskName = "NanobotFileIndexAdmin"
$watchdogRoot = "C:\Users\user\Desktop\FIRE"
$watchdogStartup = Join-Path $watchdogRoot "scripts\nanobot_watchdog_startup.bat"
$dashboardScript = Join-Path $root "scripts\Start-NanobotDashboard.ps1"
$fileIndexScript = Join-Path $root "scripts\nanobot_file_index.py"
$pythonExe = "C:\Python314\python.exe"
$userId = "$env:USERDOMAIN\$env:USERNAME"

New-Item -ItemType Directory -Force -Path $scriptsDir, $logDir, $backupDir | Out-Null
Set-Content -LiteralPath $statusPath -Value "" -Encoding UTF8

function Write-Status {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -LiteralPath $statusPath -Value $line -Encoding UTF8
    Write-Host $line
}

trap {
    Write-Status "ERROR: $($_.Exception.Message)"
    Write-Status "ERROR at: $($_.InvocationInfo.PositionMessage)"
    exit 1
}

function Backup-ScheduledTask {
    param([string]$Name)
    $task = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($null -ne $task) {
        $backupPath = Join-Path $backupDir "$Name.xml"
        $task | Export-ScheduledTask | Set-Content -LiteralPath $backupPath -Encoding UTF8
        Write-Status "Backed up task $Name to $backupPath"
    }
}

function Disable-StartupShortcut {
    param([string]$Name)
    $startup = [Environment]::GetFolderPath("Startup")
    $source = Join-Path $startup $Name
    if (-not (Test-Path -LiteralPath $source)) {
        return
    }

    $disabledDir = Join-Path $startup "Disabled by Nanobot admin mode"
    New-Item -ItemType Directory -Force -Path $disabledDir | Out-Null
    Copy-Item -LiteralPath $source -Destination (Join-Path $backupDir $Name) -Force
    Move-Item -LiteralPath $source -Destination (Join-Path $disabledDir $Name) -Force
    Write-Status "Disabled startup item $Name"
}

function Get-NanobotProcessTreeIds {
    $all = @(Get-CimInstance Win32_Process)
$roots = @($all | Where-Object {
        $_.ProcessId -ne $PID -and
        $_.CommandLine -and (
            $_.CommandLine -like "*nanobot.exe gateway*" -or
            $_.CommandLine -like "*Run-NanobotOmegaSupervisor.ps1*" -or
            $_.CommandLine -like "*nanobot_watchdog.py*" -or
            $_.CommandLine -like "*nanobot_watchdog_startup.bat*" -or
            $_.CommandLine -like "*http.server*18791*"
        )
    })

    $byParent = @{}
    foreach ($proc in $all) {
        $parentId = [int]$proc.ParentProcessId
        if (-not $byParent.ContainsKey($parentId)) {
            $byParent[$parentId] = [System.Collections.Generic.List[object]]::new()
        }
        $byParent[$parentId].Add($proc)
    }

    $ids = [System.Collections.Generic.HashSet[int]]::new()
    function Add-Tree {
        param([int]$ProcId)
        if ($ids.Add($ProcId) -and $byParent.ContainsKey($ProcId)) {
            foreach ($child in $byParent[$ProcId]) {
                Add-Tree -ProcId ([int]$child.ProcessId)
            }
        }
    }

    foreach ($rootProc in $roots) {
        Add-Tree -ProcId ([int]$rootProc.ProcessId)
    }
    return @($ids)
}

Write-Status "Nanobot admin mode install started as $userId"
Write-Status "Integrity groups: $((whoami /groups | Select-String -Pattern 'Mandatory Label|Administrateurs' | ForEach-Object { $_.Line.Trim() }) -join ' | ')"

if (-not (Test-Path -LiteralPath $supervisorScript)) {
    throw "Supervisor script not found: $supervisorScript"
}
if (-not (Test-Path -LiteralPath $watchdogStartup)) {
    throw "Watchdog startup script not found: $watchdogStartup"
}
if (-not (Test-Path -LiteralPath $dashboardScript)) {
    throw "Dashboard script not found: $dashboardScript"
}
if (-not (Test-Path -LiteralPath $fileIndexScript)) {
    throw "File index script not found: $fileIndexScript"
}
if (-not (Test-Path -LiteralPath $pythonExe)) {
    $pythonExe = "python"
}

Backup-ScheduledTask -Name $taskName
Backup-ScheduledTask -Name $watchdogTaskName
Backup-ScheduledTask -Name $dashboardTaskName
Backup-ScheduledTask -Name $indexTaskName
foreach ($name in @("NanobotSelfHeal", "NanobotBackup", "NanobotLogRotate", "NanobotVeille2ememain")) {
    Backup-ScheduledTask -Name $name
}

$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

$action = New-ScheduledTaskAction `
    -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$supervisorScript`"" `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Starts Nanobot Omega supervisor with highest privileges for the dedicated Nanobot PC." `
    -Force | Out-Null
Write-Status "Registered $taskName with RunLevel Highest"

$watchdogAction = New-ScheduledTaskAction `
    -Execute "$env:SystemRoot\System32\cmd.exe" `
    -Argument "/c `"$watchdogStartup`"" `
    -WorkingDirectory $watchdogRoot
$watchdogTrigger = New-ScheduledTaskTrigger -AtLogOn -User $userId

Register-ScheduledTask `
    -TaskName $watchdogTaskName `
    -Action $watchdogAction `
    -Trigger $watchdogTrigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Starts the Nanobot Ollama watchdog with highest privileges for the dedicated Nanobot PC." `
    -Force | Out-Null
Write-Status "Registered $watchdogTaskName with RunLevel Highest"

$dashboardAction = New-ScheduledTaskAction `
    -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$dashboardScript`"" `
    -WorkingDirectory $root
$dashboardTrigger = New-ScheduledTaskTrigger -AtLogOn -User $userId

Register-ScheduledTask `
    -TaskName $dashboardTaskName `
    -Action $dashboardAction `
    -Trigger $dashboardTrigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Starts the local Nanobot dashboard on http://127.0.0.1:18791/dashboard/." `
    -Force | Out-Null
Write-Status "Registered $dashboardTaskName with RunLevel Highest"

$indexAction = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "`"$fileIndexScript`" index --max-seconds 900 --max-files 120000" `
    -WorkingDirectory $root
$indexTrigger = New-ScheduledTaskTrigger -Daily -At 4:20am

Register-ScheduledTask `
    -TaskName $indexTaskName `
    -Action $indexAction `
    -Trigger $indexTrigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Refreshes the Nanobot local file index." `
    -Force | Out-Null
Write-Status "Registered $indexTaskName with RunLevel Highest"

foreach ($name in @("NanobotSelfHeal", "NanobotBackup", "NanobotLogRotate", "NanobotVeille2ememain")) {
    $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($null -eq $existing) {
        continue
    }

    $registerParams = @{
        TaskName = $name
        Action = $existing.Actions
        Trigger = $existing.Triggers
        Settings = $existing.Settings
        Principal = $principal
        Force = $true
    }
    if (-not [string]::IsNullOrWhiteSpace($existing.Description)) {
        $registerParams.Description = $existing.Description
    }
    Register-ScheduledTask @registerParams | Out-Null
    Write-Status "Updated $name to RunLevel Highest"
}

Disable-StartupShortcut -Name "Nanobot Telegram Gateway.vbs"
Disable-StartupShortcut -Name "NanobotWatchdog.lnk"
Disable-StartupShortcut -Name "OmegaAutostart.lnk"

$stopIds = @(Get-NanobotProcessTreeIds | Sort-Object -Descending)
foreach ($processId in $stopIds) {
    try {
        Stop-Process -Id $processId -Force -ErrorAction Stop
        Write-Status "Stopped old Nanobot process $processId"
    } catch {
        Write-Status "Could not stop process ${processId}: $($_.Exception.Message)"
    }
}

Start-Sleep -Seconds 3
Start-ScheduledTask -TaskName $taskName
Write-Status "Started $taskName"
Start-ScheduledTask -TaskName $watchdogTaskName
Write-Status "Started $watchdogTaskName"
Start-ScheduledTask -TaskName $dashboardTaskName
Write-Status "Started $dashboardTaskName"
Start-ScheduledTask -TaskName $indexTaskName
Write-Status "Started $indexTaskName"

Start-Sleep -Seconds 30
$gateway = @(Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and
    $_.CommandLine -like "*nanobot.exe gateway*" -and
    $_.CommandLine -like "*config_omega.json*"
})
$listener = Get-NetTCPConnection -LocalPort 18790 -State Listen -ErrorAction SilentlyContinue
$task = Get-ScheduledTask -TaskName $taskName
$taskInfo = Get-ScheduledTaskInfo -TaskName $taskName

Write-Status "Task state: $($task.State); last result: $($taskInfo.LastTaskResult); run level: $($task.Principal.RunLevel)"
Write-Status "Gateway PIDs: $(($gateway.ProcessId -join ', '))"
Write-Status "Port 18790 listening: $([bool]$listener)"
Write-Status "Nanobot admin mode install completed"
