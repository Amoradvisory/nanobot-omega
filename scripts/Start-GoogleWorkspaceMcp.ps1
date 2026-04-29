$ErrorActionPreference = "Stop"

$root = "C:\AI\nanobot-omega"
$server = Join-Path $root "scripts\google_workspace_mcp.py"
$token = Join-Path $root "configs\google_token.json"
$credentials = Join-Path $root "configs\google_credentials.json"

if (-not (Test-Path $server)) {
    Write-Error "Nanobot Google Workspace MCP server missing: $server"
    exit 1
}

if (-not (Test-Path $credentials)) {
    Write-Error "Google credentials missing: $credentials"
    exit 1
}

if (-not (Test-Path $token)) {
    Write-Error "Google token missing: $token. Run setup_google_auth.py once."
    exit 1
}

$env:PYTHONIOENCODING = "utf-8"
Set-Location $root
& python $server
