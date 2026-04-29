$ErrorActionPreference = "Stop"

$root = "C:\AI\nanobot-omega"
$port = 18791
$logDir = Join-Path $root "logs"
$outLog = Join-Path $logDir "dashboard.log"
$errLog = Join-Path $logDir "dashboard.err.log"
$statusScript = Join-Path $root "scripts\nanobot_full_status.py"
$python = "C:\Python314\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

try {
    & $python $statusScript --write | Out-Null
} catch {
    Add-Content -LiteralPath $errLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') status refresh failed: $($_.Exception.Message)"
}

$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    exit 0
}

Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "http.server", "$port", "--bind", "127.0.0.1") `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog
