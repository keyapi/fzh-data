# Seed IvyeaOps hub_settings.json from ai_access_poc/open_webui/.env
# - assistant_* → company new-api (api.vilavi.cn/v1)
# Does NOT print secrets. Does NOT commit hub_settings.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File ai_access_poc\board\scripts\seed_ivyeaops_hub_from_owui.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$FzhRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$IvyRoot = if ($env:IVYEAOPS_ROOT) { $env:IVYEAOPS_ROOT } else { Join-Path (Split-Path $FzhRoot -Parent) "IvyeaOps-sellfox" }
$OwuiEnv = Join-Path $FzhRoot "ai_access_poc\open_webui\.env"
$HubPath = Join-Path $IvyRoot "data\hub_settings.json"
$VenvPy = Join-Path $IvyRoot "server\.venv\Scripts\python.exe"

function Write-Info($m) { Write-Host "[seed-hub] $m" -ForegroundColor Green }
function Write-Fail($m) { Write-Host "[seed-hub] $m" -ForegroundColor Red; exit 1 }

function Get-DotEnv([string]$path) {
    $map = @{}
    if (-not (Test-Path $path)) { return $map }
    Get-Content $path | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
        $k, $v = $_ -split '=', 2
        $map[$k.Trim()] = $v.Trim().Trim('"').Trim("'")
    }
    return $map
}

$envMap = Get-DotEnv $OwuiEnv
$base = $envMap["OPENAI_API_BASE_URL"]
$key = $envMap["OPENAI_API_KEY"]
if (-not $base) { $base = "https://api.vilavi.cn/v1" }
if (-not $key -or $key -match 'replace-me|sk-replace') {
    Write-Fail "OPENAI_API_KEY missing/placeholder in $OwuiEnv — get Token at https://api.vilavi.cn/"
}

$model = if ($env:IVYEA_ASSISTANT_MODEL) { $env:IVYEA_ASSISTANT_MODEL } else { "deepseek-v4-flash" }

New-Item -ItemType Directory -Force -Path (Split-Path $HubPath) | Out-Null

$py = if (Test-Path $VenvPy) { $VenvPy } else { "python" }
$tmp = [System.IO.Path]::GetTempFileName() + ".json"

$patchObj = @{
    assistant_provider = "openai"
    assistant_base_url = $base
    assistant_api_key = $key
    assistant_model = $model
    text_ai_providers = "assistant,ivyea-agent,deepseek"
    lingxing_enabled = $true
    lingxing_operate_enabled = $false
    setup_done = $true
}
# UTF-8 no BOM — Python json.loads rejects BOM from PowerShell Set-Content -Encoding utf8
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($tmp, ($patchObj | ConvertTo-Json -Compress), $utf8NoBom)

& $py -c @"
import json, pathlib
hub = pathlib.Path(r'''$HubPath''')
raw = pathlib.Path(r'''$tmp''').read_text(encoding='utf-8-sig')
patch = json.loads(raw)
data = {}
if hub.is_file():
    data = json.loads(hub.read_text(encoding='utf-8-sig'))
data.update(patch)
hub.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print('ok', hub)
print('assistant_base_url=', data.get('assistant_base_url'))
print('assistant_model=', data.get('assistant_model'))
print('key_len=', len(str(data.get('assistant_api_key') or '')))
"@

Remove-Item -Force $tmp -ErrorAction SilentlyContinue
Write-Info "Seeded hub_settings (assistant → new-api). Restart IvyeaOps if already running."
