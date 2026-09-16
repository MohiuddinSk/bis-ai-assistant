[CmdletBinding()]
param(
    [int]$TimeoutSeconds = 15
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$ProjectName = "sih-secure-demo"
$FrontendHostname = [Environment]::GetEnvironmentVariable("SIH_FRONTEND_HOSTNAME", "Process")
$ApiHostname = [Environment]::GetEnvironmentVariable("SIH_API_HOSTNAME", "Process")
if ([string]::IsNullOrWhiteSpace($FrontendHostname) -or [string]::IsNullOrWhiteSpace($ApiHostname)) { throw "SIH_FRONTEND_HOSTNAME and SIH_API_HOSTNAME must be set before checking the demo." }
if ($TimeoutSeconds -le 0) { throw "TimeoutSeconds must be positive." }

docker compose -f (Join-Path $Root "compose.yaml") -p $ProjectName ps backend
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the demo backend." }
$LocalHealth = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -TimeoutSec $TimeoutSeconds
if ($LocalHealth.status -ne "ready") { throw "Local backend health check did not report ready." }
$PublicHealth = Invoke-RestMethod -Uri "https://$ApiHostname/api/v1/health" -TimeoutSec $TimeoutSeconds
if ($PublicHealth.status -ne "ready") { throw "Named-tunnel health check did not report ready." }
Write-Output "Secure SIH demo checks passed for configured frontend and API hostnames."
