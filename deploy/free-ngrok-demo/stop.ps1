[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\\..")).Path
$RuntimeDirectory = Join-Path $PSScriptRoot ".runtime"
$StatePath = Join-Path $RuntimeDirectory "ngrok-process.json"
$ProjectName = "free-ngrok-demo"

if (Test-Path -LiteralPath $StatePath -PathType Leaf) {
    try { $State = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json -ErrorAction Stop } catch { $State = $null }
    if ($null -ne $State -and $State.pid -match '^\d+$' -and -not [string]::IsNullOrWhiteSpace($State.started_utc)) {
        $TunnelProcess = Get-Process -Id ([int]$State.pid) -ErrorAction SilentlyContinue
        if ($null -ne $TunnelProcess -and $TunnelProcess.ProcessName -match '^ngrok(?:\.exe)?$' -and $TunnelProcess.StartTime.ToUniversalTime().ToString("o") -eq [string]$State.started_utc) {
            Stop-Process -Id $TunnelProcess.Id -ErrorAction Stop
        }
    }
    Remove-Item -LiteralPath $StatePath -Force
}

docker compose -f (Join-Path $Root "compose.yaml") -p $ProjectName down
if ($LASTEXITCODE -ne 0) { throw "free-ngrok-demo: backend-stop-failed" }
Write-Output "Free ngrok demo resources stopped."
