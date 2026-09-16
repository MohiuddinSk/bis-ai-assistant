[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$RuntimeDirectory = Join-Path $PSScriptRoot ".secure-sih-demo-runtime"
$StatePath = Join-Path $RuntimeDirectory "cloudflared.pid"
$ProjectName = "sih-secure-demo"

if (Test-Path -LiteralPath $StatePath -PathType Leaf) {
    $PidText = (Get-Content -LiteralPath $StatePath -Raw).Trim()
    if ($PidText -match '^\d+$') {
        $TunnelProcess = Get-Process -Id ([int]$PidText) -ErrorAction SilentlyContinue
        if ($null -ne $TunnelProcess -and $TunnelProcess.ProcessName -match '^cloudflared(?:\.exe)?$') {
            Stop-Process -Id $TunnelProcess.Id -ErrorAction Stop
        }
    }
    Remove-Item -LiteralPath $StatePath -Force
}

docker compose -f (Join-Path $Root "compose.yaml") -p $ProjectName down
if ($LASTEXITCODE -ne 0) { throw "Could not stop only the secure SIH demo Compose project." }
Write-Output "Secure SIH demo resources stopped."
