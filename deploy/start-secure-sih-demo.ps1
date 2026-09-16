[CmdletBinding()]
param(
    [switch]$EnableGeneration
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$RuntimeDirectory = Join-Path $PSScriptRoot ".secure-sih-demo-runtime"
$StatePath = Join-Path $RuntimeDirectory "cloudflared.pid"
$ProjectName = "sih-secure-demo"

function Get-RequiredHostname {
    param([string]$Name)
    $Value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -notmatch '^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$') {
        throw "$Name must be an explicit DNS hostname without a scheme, path, or wildcard."
    }
    return $Value.ToLowerInvariant()
}

function Get-RequiredValue {
    param([string]$Name)
    $Value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($Value)) { throw "$Name must be set." }
    return $Value.Trim()
}

function Test-ExistingTunnelProcess {
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) { return $false }
    $PidText = (Get-Content -LiteralPath $StatePath -Raw).Trim()
    if ($PidText -notmatch '^\d+$') { Remove-Item -LiteralPath $StatePath -Force; return $false }
    $Existing = Get-Process -Id ([int]$PidText) -ErrorAction SilentlyContinue
    if ($null -eq $Existing -or $Existing.ProcessName -notmatch '^cloudflared(?:\.exe)?$') {
        Remove-Item -LiteralPath $StatePath -Force
        return $false
    }
    return $true
}

$FrontendHostname = Get-RequiredHostname "SIH_FRONTEND_HOSTNAME"
$ApiHostname = Get-RequiredHostname "SIH_API_HOSTNAME"
$TunnelName = Get-RequiredValue "SIH_TUNNEL_NAME"
$CloudflaredConfig = Get-RequiredValue "SIH_CLOUDFLARED_CONFIG"
if (-not (Test-Path -LiteralPath $CloudflaredConfig -PathType Leaf)) { throw "SIH_CLOUDFLARED_CONFIG must point to an existing local Cloudflare configuration file." }
if ($FrontendHostname -eq $ApiHostname) { throw "SIH_FRONTEND_HOSTNAME and SIH_API_HOSTNAME must be different hostnames." }
Get-Command docker -ErrorAction Stop | Out-Null
$CloudflaredCommand = Get-Command cloudflared -ErrorAction Stop

$OriginalEnvironment = @{}
foreach ($Name in @("ALLOWED_ORIGINS", "BACKEND_HOST_PORT", "LLM_PROVIDER", "GROQ_API_KEY", "LLM_API_KEY")) {
    $OriginalEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
}

try {
    [Environment]::SetEnvironmentVariable("BACKEND_HOST_PORT", "8000", "Process")
    [Environment]::SetEnvironmentVariable("ALLOWED_ORIGINS", "https://$FrontendHostname", "Process")
    if (-not $EnableGeneration) {
        [Environment]::SetEnvironmentVariable("LLM_PROVIDER", "disabled", "Process")
        [Environment]::SetEnvironmentVariable("GROQ_API_KEY", "", "Process")
        [Environment]::SetEnvironmentVariable("LLM_API_KEY", "", "Process")
    }
    else {
        $Provider = Get-RequiredValue "LLM_PROVIDER"
        if ($Provider -eq "disabled") { throw "-EnableGeneration requires a configured non-disabled LLM_PROVIDER." }
        if ($Provider -eq "groq" -and [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable("GROQ_API_KEY", "Process"))) { throw "-EnableGeneration with groq requires GROQ_API_KEY." }
        if ($Provider -eq "openai_compatible" -and [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable("LLM_API_KEY", "Process"))) { throw "-EnableGeneration with openai_compatible requires LLM_API_KEY." }
    }

    docker compose -f (Join-Path $Root "compose.yaml") -p $ProjectName up --build --detach backend
    if ($LASTEXITCODE -ne 0) { throw "Backend Compose startup failed." }

    New-Item -ItemType Directory -Path $RuntimeDirectory -Force | Out-Null
    if (-not (Test-ExistingTunnelProcess)) {
        $StartInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $StartInfo.FileName = $CloudflaredCommand.Source
        $StartInfo.UseShellExecute = $false
        [void]$StartInfo.ArgumentList.Add("--config")
        [void]$StartInfo.ArgumentList.Add($CloudflaredConfig)
        [void]$StartInfo.ArgumentList.Add("tunnel")
        [void]$StartInfo.ArgumentList.Add("run")
        [void]$StartInfo.ArgumentList.Add($TunnelName)
        $TunnelProcess = [System.Diagnostics.Process]::Start($StartInfo)
        if ($null -eq $TunnelProcess) { throw "Named tunnel process could not be started." }
        Set-Content -LiteralPath $StatePath -Value $TunnelProcess.Id -NoNewline
    }
    Write-Output "Secure SIH demo backend started. Use https://$ApiHostname as Netlify VITE_API_BASE_URL."
}
finally {
    foreach ($Name in $OriginalEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($Name, $OriginalEnvironment[$Name], "Process")
    }
}
