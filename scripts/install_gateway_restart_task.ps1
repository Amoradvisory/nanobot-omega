#requires -RunAsAdministrator
# Cree (ou met a jour) la tache planifiee NanobotGatewayRestart qui peut
# ensuite etre declenchee par schtasks /Run sans privilege admin.
#
# Action : kill le gateway courant (PID dans state/gateway.lock) puis
# trigger NanobotOmegaSupervisorAdmin qui spawn un gateway frais.
#
# Une fois cette tache installee, plus aucun UAC n'est necessaire pour
# redemarrer le gateway.

$ErrorActionPreference = "Stop"
$taskName = "NanobotGatewayRestart"
$wrapper = "C:\AI\nanobot-omega\scripts\gateway_restart_action.ps1"
$logFile = "C:\AI\nanobot-omega\logs\gateway_restart.log"

# Action script (le wrapper) — recree a chaque install pour rester a jour.
$action = @'
$ErrorActionPreference = "Continue"
$logFile = "C:\AI\nanobot-omega\logs\gateway_restart.log"
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$ts] === NanobotGatewayRestart triggered ===" | Out-File $logFile -Append -Encoding utf8
try {
    $lock = Get-Content "C:\AI\nanobot-omega\state\gateway.lock" -Raw -ErrorAction Stop | ConvertFrom-Json
    $oldPid = [int]$lock.pid
    "[$ts] Old gateway PID: $oldPid" | Out-File $logFile -Append -Encoding utf8
    Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
    "[$ts] Stop-Process issued" | Out-File $logFile -Append -Encoding utf8
} catch {
    "[$ts] Lock unreadable: $_" | Out-File $logFile -Append -Encoding utf8
}
Start-Sleep -Seconds 3
try {
    Start-ScheduledTask -TaskName 'NanobotOmegaSupervisorAdmin' -ErrorAction Stop
    "[$ts] Supervisor triggered" | Out-File $logFile -Append -Encoding utf8
} catch {
    "[$ts] Supervisor trigger failed: $_" | Out-File $logFile -Append -Encoding utf8
}
'@

# Ecrit le wrapper
$wrapperDir = Split-Path $wrapper -Parent
if (-not (Test-Path $wrapperDir)) { New-Item -ItemType Directory -Path $wrapperDir -Force | Out-Null }
Set-Content -Path $wrapper -Value $action -Encoding utf8

# (Re)create the task
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$taskAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$wrapper`""
$taskPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::FromMinutes(2))
Register-ScheduledTask -TaskName $taskName -Action $taskAction -Principal $taskPrincipal -Settings $taskSettings -Description "Kill gateway lock pid + relance supervisor. Triggerable sans admin via schtasks /Run."

# Allow non-admin users to trigger this task by setting an explicit DACL via SDDL.
# We use sd /grant to allow the Users group to read+execute the task.
# Easier approach: use the COM API ITaskFolder.RegisterTaskDefinition with security descriptor.
# Simpler still: Set-ScheduledTask + ScheduledTask SDDL via cim.
$sddl = "D:AI(A;;GA;;;BA)(A;;GRGX;;;BU)"  # admins full, users read+execute (trigger)
schtasks /Change /TN $taskName /RU "SYSTEM" /RL HIGHEST 2>&1 | Out-Null
# Set DACL via Set-Acl on task XML in C:\Windows\System32\Tasks\NanobotGatewayRestart
$taskXmlPath = "C:\Windows\System32\Tasks\$taskName"
if (Test-Path $taskXmlPath) {
    try {
        $acl = Get-Acl $taskXmlPath
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule("Users", "ReadAndExecute", "Allow")
        $acl.AddAccessRule($rule)
        Set-Acl -Path $taskXmlPath -AclObject $acl
    } catch {
        "Could not set ACL: $_" | Out-File $logFile -Append -Encoding utf8
    }
}

"OK : tache $taskName installee. Trigger : schtasks /Run /TN $taskName"
"Test maintenant : Start-ScheduledTask -TaskName $taskName"
