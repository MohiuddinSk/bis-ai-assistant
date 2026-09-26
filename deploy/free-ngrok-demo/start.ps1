[CmdletBinding()]
param([switch]$EnableGeneration, [int]$TimeoutSeconds = 60)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\\..")).Path
$RuntimeDirectory = Join-Path $PSScriptRoot ".runtime"
$StatePath = Join-Path $RuntimeDirectory "ngrok-process.json"
$ProjectName = "free-ngrok-demo"
$AgentApiUri = "http://127.0.0.1:4040/api/tunnels"
function Stop-WithReason { param([string]$Reason) ; throw "free-ngrok-demo: $Reason" }
function Assert-Condition { param([bool]$Condition, [string]$Reason) ; if (-not $Condition) { Stop-WithReason $Reason } }
function Get-RequiredNgrokHostname {
    $Value = [Environment]::GetEnvironmentVariable("FREE_NGROK_HTTPS_HOSTNAME", "Process")
    if ([string]::IsNullOrWhiteSpace($Value)) { Stop-WithReason "missing-api-hostname" }
    $Hostname = $Value.Trim().ToLowerInvariant()
    if ($Hostname -notmatch '^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$' -or $Hostname -notmatch '\.ngrok-free\.(?:app|dev)$') { Stop-WithReason "invalid-api-hostname" }
    return $Hostname
}
function Get-RequiredFrontendOrigin {
    $Value = [Environment]::GetEnvironmentVariable("FREE_NGROK_FRONTEND_ORIGIN", "Process")
    if ([string]::IsNullOrWhiteSpace($Value)) { Stop-WithReason "missing-frontend-origin" }
    $Origin = $Value.Trim()
    if ($Origin -notmatch '^https://(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$') { Stop-WithReason "invalid-frontend-origin" }
    return $Origin.ToLowerInvariant()
}
function Get-TrackedNgrokProcess {
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) { return $null }
    try { $State = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json -ErrorAction Stop } catch { Remove-Item -LiteralPath $StatePath -Force; return $null }
    if ($State.pid -notmatch '^\d+$' -or [string]::IsNullOrWhiteSpace($State.started_utc)) { Remove-Item -LiteralPath $StatePath -Force; return $null }
    $Process = Get-Process -Id ([int]$State.pid) -ErrorAction SilentlyContinue
    if ($null -eq $Process -or $Process.ProcessName -notmatch '^ngrok(?:\.exe)?$' -or $Process.StartTime.ToUniversalTime().ToString("o") -ne [string]$State.started_utc) { Remove-Item -LiteralPath $StatePath -Force; return $null }
    return $Process
}
function Get-ExpectedTunnel { param([string]$ExpectedPublicUrl)
    try { $Agent = Invoke-RestMethod -Uri $AgentApiUri -TimeoutSec 2 -ErrorAction Stop } catch { return $null }
    $Matches = @($Agent.tunnels | Where-Object { $_.public_url -ceq $ExpectedPublicUrl })
    if ($Matches.Count -ne 1) { return $null }
    $Tunnel = $Matches[0]
    if ($Tunnel.proto -cne "https" -or $Tunnel.config.addr -cne "http://127.0.0.1:8000") { return $null }
    return $Tunnel
}
function Wait-ForCondition { param([scriptblock]$Condition, [string]$Reason, [int]$Timeout)
    $Deadline = (Get-Date).AddSeconds($Timeout)
    do { if (& $Condition) { return }; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $Deadline)
    Stop-WithReason $Reason
}
function Wait-ForPublicHealth { param([string]$Uri, [int]$Timeout)
    $Deadline = (Get-Date).AddSeconds($Timeout); $LastState = "network"
    do {
        try {
            $Response = Invoke-WebRequest -Uri $Uri -TimeoutSec 2 -Headers @{ "ngrok-skip-browser-warning" = "1" } -ErrorAction Stop
            try { $Body = $Response.Content | ConvertFrom-Json -ErrorAction Stop } catch { $LastState = "non-json"; Start-Sleep -Milliseconds 500; continue }
            if ($Response.StatusCode -eq 200 -and $Body.status -eq "ready") { return }
            $LastState = "health-not-ready"
        } catch { $LastState = "network" }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $Deadline)
    if ($LastState -eq "non-json") { Stop-WithReason "public-health-non-json-response" }
    if ($LastState -eq "network") { Stop-WithReason "public-health-network-timeout" }
    Stop-WithReason "public-health-not-ready"
}
function Stop-OwnedResources { param([System.Diagnostics.Process]$Process, [bool]$StopBackend)
    if ($null -ne $Process -and -not $Process.HasExited -and $Process.ProcessName -match '^ngrok(?:\.exe)?$') { Stop-Process -Id $Process.Id -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $StatePath -PathType Leaf) { Remove-Item -LiteralPath $StatePath -Force }
    if ($StopBackend) { docker compose -f (Join-Path $Root "compose.yaml") -p $ProjectName down 2>$null | Out-Null }
}

$ApiHostname = Get-RequiredNgrokHostname
$FrontendOrigin = Get-RequiredFrontendOrigin
$ExpectedPublicUrl = "https://$ApiHostname"
Assert-Condition ($TimeoutSeconds -gt 0 -and $TimeoutSeconds -le 300) "invalid-timeout"
Get-Command docker -ErrorAction Stop | Out-Null
$NgrokCommand = Get-Command ngrok -ErrorAction Stop
if ($null -ne (Get-TrackedNgrokProcess)) { Stop-WithReason "demo-ngrok-already-running" }
$ExistingBackendContainer = docker compose -f (Join-Path $Root "compose.yaml") -p $ProjectName ps -q backend 2>$null
$BackendStartedByScript = [string]::IsNullOrWhiteSpace([string]$ExistingBackendContainer)
$OriginalEnvironment = @{}
foreach ($Name in @("ALLOWED_ORIGINS", "BACKEND_HOST_PORT", "LLM_PROVIDER", "GROQ_API_KEY", "LLM_API_KEY")) { $OriginalEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process") }
$TunnelProcess = $null; $Succeeded = $false
try {
    [Environment]::SetEnvironmentVariable("BACKEND_HOST_PORT", "8000", "Process")
    [Environment]::SetEnvironmentVariable("ALLOWED_ORIGINS", $FrontendOrigin, "Process")
    if (-not $EnableGeneration) {
        [Environment]::SetEnvironmentVariable("LLM_PROVIDER", "disabled", "Process")
        [Environment]::SetEnvironmentVariable("GROQ_API_KEY", "", "Process")
        [Environment]::SetEnvironmentVariable("LLM_API_KEY", "", "Process")
    } elseif ([Environment]::GetEnvironmentVariable("LLM_PROVIDER", "Process") -eq "disabled" -or [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable("LLM_PROVIDER", "Process"))) { Stop-WithReason "generation-provider-not-configured" }
    docker compose -f (Join-Path $Root "compose.yaml") -p $ProjectName up --build --detach backend
    if ($LASTEXITCODE -ne 0) { Stop-WithReason "backend-start-failed" }
    Wait-ForCondition { $ContainerId = docker compose -f (Join-Path $Root "compose.yaml") -p $ProjectName ps -q backend; $ContainerId -and (docker inspect --format '{{.State.Health.Status}}' $ContainerId 2>$null) -eq "healthy" } "backend-health-timeout" $TimeoutSeconds
    New-Item -ItemType Directory -Path $RuntimeDirectory -Force | Out-Null
    $StartInfo = [System.Diagnostics.ProcessStartInfo]::new(); $StartInfo.FileName = $NgrokCommand.Source; $StartInfo.UseShellExecute = $false; $StartInfo.RedirectStandardOutput = $true; $StartInfo.RedirectStandardError = $true
    [void]$StartInfo.ArgumentList.Add("http"); [void]$StartInfo.ArgumentList.Add("http://127.0.0.1:8000")
    $TunnelProcess = [System.Diagnostics.Process]::Start($StartInfo)
    if ($null -eq $TunnelProcess) { Stop-WithReason "ngrok-start-failed" }
    $TunnelProcess.BeginOutputReadLine(); $TunnelProcess.BeginErrorReadLine()
    @{ pid = $TunnelProcess.Id; started_utc = $TunnelProcess.StartTime.ToUniversalTime().ToString("o"); api_hostname = $ApiHostname } | ConvertTo-Json -Compress | Set-Content -LiteralPath $StatePath -NoNewline
    Wait-ForCondition { -not $TunnelProcess.HasExited } "ngrok-exited-early" $TimeoutSeconds
    Wait-ForCondition { if ($TunnelProcess.HasExited) { Stop-WithReason "ngrok-exited-early" }; $null -ne (Get-ExpectedTunnel $ExpectedPublicUrl) } "expected-tunnel-not-registered" $TimeoutSeconds
    if ($TunnelProcess.HasExited) { Stop-WithReason "ngrok-exited-early" }
    Wait-ForPublicHealth "$ExpectedPublicUrl/health" $TimeoutSeconds
    $Succeeded = $true
    Write-Output "Free ngrok demo started. Configure the frontend VITE_API_BASE_URL as $ExpectedPublicUrl."
} finally {
    if (-not $Succeeded) { Stop-OwnedResources $TunnelProcess $BackendStartedByScript }
    foreach ($Name in $OriginalEnvironment.Keys) { [Environment]::SetEnvironmentVariable($Name, $OriginalEnvironment[$Name], "Process") }
}
