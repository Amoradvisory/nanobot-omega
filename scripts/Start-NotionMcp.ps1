$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($env:NOTION_TOKEN)) {
    $userToken = [Environment]::GetEnvironmentVariable("NOTION_TOKEN", "User")
    if (-not [string]::IsNullOrWhiteSpace($userToken)) {
        $env:NOTION_TOKEN = $userToken
    }
}

if ([string]::IsNullOrWhiteSpace($env:NOTION_TOKEN)) {
    $machineToken = [Environment]::GetEnvironmentVariable("NOTION_TOKEN", "Machine")
    if (-not [string]::IsNullOrWhiteSpace($machineToken)) {
        $env:NOTION_TOKEN = $machineToken
    }
}

if ([string]::IsNullOrWhiteSpace($env:NOTION_TOKEN)) {
    Write-Error "NOTION_TOKEN is missing. Create a Notion internal integration token and store it in the User environment."
    exit 1
}

& "C:/nvm4w/nodejs/npx.cmd" -y "@notionhq/notion-mcp-server"
