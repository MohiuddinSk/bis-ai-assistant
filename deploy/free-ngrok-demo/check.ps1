[CmdletBinding()]
param([int]$TimeoutSeconds = 30)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\\..")).Path
$ProjectName = "free-ngrok-demo"
$AgentApiUri = "http://127.0.0.1:4040/api/tunnels"
function Stop-WithReason { param([string]$Reason) ; throw "free-ngrok-demo: $Reason" }
function Assert-Condition { param([bool]$Condition, [string]$Reason) ; if (-not $Condition) { Stop-WithReason $Reason } }
function Get-RequiredNgrokHostname { $Value = [Environment]::GetEnvironmentVariable("FREE_NGROK_HTTPS_HOSTNAME", "Process"); if ([string]::IsNullOrWhiteSpace($Value)) { Stop-WithReason "missing-api-hostname" }; $Hostname = $Value.Trim().ToLowerInvariant(); if ($Hostname -notmatch '^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$' -or $Hostname -notmatch '\.ngrok-free\.(?:app|dev)$') { Stop-WithReason "invalid-api-hostname" }; return $Hostname }
function Get-RequiredFrontendOrigin { $Value = [Environment]::GetEnvironmentVariable("FREE_NGROK_FRONTEND_ORIGIN", "Process"); if ([string]::IsNullOrWhiteSpace($Value)) { Stop-WithReason "missing-frontend-origin" }; $Origin = $Value.Trim(); if ($Origin -notmatch '^https://[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$' -or $Origin -notmatch '^https://[^/]+\.netlify\.app$') { Stop-WithReason "invalid-frontend-origin" }; return $Origin.ToLowerInvariant() }
function Get-ExpectedTunnel { param([string]$ExpectedPublicUrl)
    try { $Agent = Invoke-RestMethod -Uri $AgentApiUri -TimeoutSec 2 -ErrorAction Stop } catch { return $null }
    $Matches = @($Agent.tunnels | Where-Object { $_.public_url -ceq $ExpectedPublicUrl })
    if ($Matches.Count -ne 1 -or $Matches[0].proto -cne "https" -or $Matches[0].config.addr -cne "http://127.0.0.1:8000") { return $null }; return $Matches[0]
}
function Wait-ForCondition { param([scriptblock]$Condition, [string]$Reason, [int]$Timeout)
    $Deadline = (Get-Date).AddSeconds($Timeout); do { if (& $Condition) { return }; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $Deadline); Stop-WithReason $Reason
}
function Wait-ForHealth { param([string]$Base, [string]$Path, [int]$Timeout)
    $Deadline = (Get-Date).AddSeconds($Timeout); $LastState = "network"
    $Headers = @{ "X-Request-ID" = "free-ngrok-check-001" }
    if ($Base -ceq $ExpectedPublicUrl) { $Headers["ngrok-skip-browser-warning"] = "1" }
    do {
        try {
            $Response = Invoke-WebRequest -Uri "$Base$Path" -TimeoutSec 2 -Headers $Headers -ErrorAction Stop
            try { $Body = $Response.Content | ConvertFrom-Json -ErrorAction Stop } catch { $LastState = "non-json"; Start-Sleep -Milliseconds 500; continue }
            if ($Response.StatusCode -eq 200 -and $Body.status -eq "ready" -and @($Response.Headers["X-Request-ID"]).Count -eq 1 -and [string]$Response.Headers["X-Request-ID"] -ceq "free-ngrok-check-001") { return }
            $LastState = "health-or-request-id"
        } catch { $LastState = "network" }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $Deadline)
    if ($Base -ceq $ExpectedPublicUrl -and $LastState -eq "non-json") { Stop-WithReason "public-health-non-json-response" }
    if ($LastState -eq "network") { Stop-WithReason "health-network-timeout" }
    Stop-WithReason "health-or-request-id-failed"
}
$ApiHostname = Get-RequiredNgrokHostname; $FrontendOrigin = Get-RequiredFrontendOrigin; $ExpectedPublicUrl = "https://$ApiHostname"
Assert-Condition ($TimeoutSeconds -gt 0 -and $TimeoutSeconds -le 300) "invalid-timeout"
docker compose -f (Join-Path $Root "compose.yaml") -p $ProjectName ps backend
if ($LASTEXITCODE -ne 0) { Stop-WithReason "backend-status-unavailable" }
Wait-ForCondition { $null -ne (Get-ExpectedTunnel $ExpectedPublicUrl) } "expected-tunnel-not-registered" $TimeoutSeconds
foreach ($Base in @("http://127.0.0.1:8000", $ExpectedPublicUrl)) { foreach ($Path in @("/health", "/api/v1/health")) { Wait-ForHealth $Base $Path $TimeoutSeconds } }
$Cors = $null
Wait-ForCondition { try { $Cors = Invoke-WebRequest -Uri "$ExpectedPublicUrl/api/v1/retrieve" -Method OPTIONS -TimeoutSec 2 -Headers @{ Origin = $FrontendOrigin; "Access-Control-Request-Method" = "POST"; "Access-Control-Request-Headers" = "content-type,x-request-id,ngrok-skip-browser-warning"; "ngrok-skip-browser-warning" = "1" } -ErrorAction Stop; $Cors.StatusCode -eq 200 -and [string]$Cors.Headers["Access-Control-Allow-Origin"] -ceq $FrontendOrigin } catch { $false } } "cors-origin-mismatch" $TimeoutSeconds
foreach ($Path in @("/api/retrieve", "/api/v1/retrieve", "/api/chat", "/api/v1/chat")) { Wait-ForCondition { try { (Invoke-WebRequest -Uri "$ExpectedPublicUrl$Path" -Method POST -ContentType "application/json" -Body '{"question":"what standards apply to a battery-operated toy"}' -Headers @{ "ngrok-skip-browser-warning" = "1" } -TimeoutSec 2 -ErrorAction Stop).StatusCode -eq 200 } catch { $false } } "route-validation-failed" $TimeoutSeconds }
$EnvironmentEntries = @(docker compose -f (Join-Path $Root "compose.yaml") -p $ProjectName exec -T backend printenv 2>$null)
foreach ($Name in @("GROQ_API_KEY", "LLM_API_KEY")) { $Entries = @($EnvironmentEntries | Where-Object { $_ -is [string] -and $_.StartsWith("$Name=", [System.StringComparison]::Ordinal) }); Assert-Condition ($Entries.Count -eq 1 -and $Entries[0].EndsWith("=")) "provider-secret-present" }
Write-Output "Free ngrok demo checks passed."
