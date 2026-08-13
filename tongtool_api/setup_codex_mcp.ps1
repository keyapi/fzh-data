param(
    [string]$EnvFile = (Join-Path $PSScriptRoot ".env")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Missing $EnvFile. Copy .env.example to .env and fill the local credentials."
}

$values = @{}
foreach ($line in Get-Content -LiteralPath $EnvFile) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
    $parts = $trimmed.Split("=", 2)
    if ($parts.Count -eq 2) {
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
}

function Get-CredentialPair([string]$KeyName, [string]$SecretName) {
    $key = $values[$KeyName]
    $secret = $values[$SecretName]
    if (($key -and -not $secret) -or ($secret -and -not $key)) {
        throw "$KeyName and $SecretName must be configured together."
    }
    return @($key, $secret)
}

$primary = Get-CredentialPair "TONGTOOL_ERP2_PRIMARY_KEY" "TONGTOOL_ERP2_PRIMARY_SECRET"
$secondary = Get-CredentialPair "TONGTOOL_ERP2_SECONDARY_KEY" "TONGTOOL_ERP2_SECONDARY_SECRET"
if (-not $primary[0] -and -not $secondary[0]) {
    throw "No Tongtool ERP2 credentials configured."
}

$configDir = Join-Path $HOME ".codex"
$configPath = Join-Path $configDir "config.toml"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
$content = if (Test-Path -LiteralPath $configPath) {
    Get-Content -LiteralPath $configPath -Raw
} else {
    ""
}

$begin = "# BEGIN managed tongtool_api MCP"
$end = "# END managed tongtool_api MCP"
$start = $content.IndexOf($begin)
if ($start -ge 0) {
    $finish = $content.IndexOf($end, $start)
    if ($finish -lt 0) { throw "Found Tongtool MCP begin marker without end marker." }
    $finish += $end.Length
    $content = $content.Remove($start, $finish - $start)
}

$blocks = New-Object System.Collections.Generic.List[string]
function Add-McpServer([string]$Name, [string]$Key, [string]$Secret) {
    if (-not $Key) { return }
    $escapedKey = $Key.Replace("\", "\\").Replace('"', '\"')
    $escapedSecret = $Secret.Replace("\", "\\").Replace('"', '\"')
    $block = @"
[mcp_servers.$Name]
url = "https://mcp.tongtool.com/mcp"
http_headers = { "x-tongtool-access-key" = "$escapedKey", "x-tongtool-secret-key" = "$escapedSecret" }
"@
    $blocks.Add($block.Trim())
}

Add-McpServer "tongtool_erp2_primary" $primary[0] $primary[1]
Add-McpServer "tongtool_erp2_secondary" $secondary[0] $secondary[1]

$managed = $begin + [Environment]::NewLine +
    ($blocks -join ([Environment]::NewLine * 2)) + [Environment]::NewLine + $end
$newContent = $content.TrimEnd() + [Environment]::NewLine * 2 + $managed + [Environment]::NewLine
Set-Content -LiteralPath $configPath -Value $newContent -Encoding utf8

Write-Host "Registered $($blocks.Count) Tongtool ERP2 MCP server(s) in $configPath"
Write-Host "Fully quit and restart Codex to reload MCP configuration."
