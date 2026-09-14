[CmdletBinding()]
param(
    [int]$TimeoutSeconds = 180,
    [int]$HostPort = 18000
)

$ErrorActionPreference = 'Stop'
$Image = 'bis-saarthi-backend:prototype'
$Name = "bis-saarthi-container-test-$PID"
$Root = Split-Path -Parent $PSScriptRoot
$Allowed = @('backend/chat_service.py', 'backend/main.py', 'backend/service.py', 'backend/settings.py', 'backend/retrieval_factory.py', 'backend/retrieval_provider.py', 'compose.yaml', 'docs/BIS_INTEGRATION_READINESS.md', 'docs/CONTAINER_DEPLOYMENT.md', 'scripts/test_container.ps1', 'tests/test_api.py', 'tests/test_chat_api.py', 'tests/test_container_configuration.py', 'tests/test_retrieval_disabled_api.py', 'tests/test_retrieval_factory.py', 'tests/test_retrieval_provider_contract.py')

function Assert-True([bool]$Value, [string]$Message) { if (-not $Value) { throw $Message } }
function Get-Json([string]$Path, [hashtable]$Headers = @{}) {
    return Invoke-RestMethod -Uri "http://127.0.0.1:$HostPort$Path" -Headers $Headers -TimeoutSec 10
}
function Get-Web([string]$Path, [hashtable]$Headers = @{}) {
    return Invoke-WebRequest -Uri "http://127.0.0.1:$HostPort$Path" -Headers $Headers -TimeoutSec 10
}
function Stop-TestContainer {
    if ((docker ps -aq --filter "name=^/$Name") -as [string]) {
        docker rm -f $Name | Out-Null
    }
}

try {
    docker version --format '{{.Server.Version}}' | Out-Null
    $changes = @(git -C $Root status --porcelain=v1 --untracked-files=all | ForEach-Object {
        $line = $_
        if ([string]::IsNullOrWhiteSpace($line)) { return }
        if ($line.Length -lt 4 -or $line[2] -ne ' ') { throw "Unparseable git status entry." }
        $status = $line.Substring(0, 2)
        $path = $line.Substring(3).Replace('\', '/')
        if ($status -match '[RD]' -or $path.Contains(' -> ') -or $path.StartsWith('/') -or $path.Contains('..') -or $path.Contains('"')) { throw "Unsafe git status entry." }
        [pscustomobject]@{ Status = $status; Path = $path }
    })
    $unexpected = @($changes | Where-Object { $_.Path -notin $Allowed })
    $unexpectedPaths = @(
        $unexpected |
        ForEach-Object { $_.Path }
    )
    Assert-True ($unexpected.Count -eq 0) "Unexpected working-tree modifications: $($unexpectedPaths -join ', ')"

    Remove-Item Env:GROQ_API_KEY -ErrorAction SilentlyContinue
    docker build --tag $Image $Root

    $portInUse = Get-NetTCPConnection -LocalPort $HostPort -State Listen -ErrorAction SilentlyContinue
    Assert-True ($null -eq $portInUse) "Host port $HostPort is already listening; choose -HostPort."
    docker run --detach --name $Name --init --cap-drop ALL --security-opt no-new-privileges:true --tmpfs /tmp:rw,nosuid,nodev,size=64m -p "${HostPort}:8000" -e RETRIEVAL_PROVIDER=chroma_local -e LLM_PROVIDER=disabled -e GROQ_API_KEY= -e LLM_API_KEY= $Image | Out-Null

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $health = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' $Name
        if ($health -eq 'healthy') { break }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    if ($health -ne 'healthy') { docker logs --tail 120 $Name; throw "Container did not become healthy." }

    Assert-True ((docker inspect --format '{{.State.Running}}' $Name) -eq 'true') 'Container is not running.'
    $legacy = Get-Json '/health'; $v1 = Get-Json '/api/v1/health'
    Assert-True ($legacy.status -eq 'ready' -and $v1.status -eq 'ready') 'Health response is not ready.'
    Assert-True ($legacy.collection_count -eq 917 -and $v1.collection_count -eq 917) 'Expected collection_count 917.'
    $requestId = 'container-test-request-001'
    $response = Get-Web '/api/v1/health' @{ 'X-Request-ID' = $requestId }
    $responseRequestIds = @($response.Headers['X-Request-ID'])
    $requestIdWasPreserved = (
        $responseRequestIds.Count -eq 1 -and
        $responseRequestIds[0] -is [string] -and
        [string]$responseRequestIds[0] -ceq $requestId
    )
    Assert-True ([bool]$requestIdWasPreserved) 'Valid X-Request-ID was not preserved.'

    $clarification = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$HostPort/api/v1/chat" -ContentType 'application/json' -Body '{"question":"what standards apply to toys"}'
    Assert-True ($clarification.needs_clarification -and $clarification.generation_mode -eq 'clarification') 'Deterministic clarification failed.'
    $profile = '{"role":"manufacturer","product_description":"Battery-operated toy car","power_type":"battery_operated","intended_age_group":"3_to_8","goal":"identify_standards","application_stage":"researching","additional_context":null}'
    $guide = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$HostPort/api/v1/compliance/guide" -ContentType 'application/json' -Body $profile
    Assert-True ($guide.guidance.grounded -and $guide.guidance.answer -match 'IS 15644') 'Deterministic compliance guidance failed.'
    $body = '{"question":"what standards apply to a battery-operated toy"}'
    $legacyRetrieve = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$HostPort/api/retrieve" -ContentType 'application/json' -Body $body
    $versionedRetrieve = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$HostPort/api/v1/retrieve" -ContentType 'application/json' -Body $body
    Assert-True ($legacyRetrieve.result_count -gt 0 -and (($legacyRetrieve | ConvertTo-Json -Depth 20 -Compress) -eq ($versionedRetrieve | ConvertTo-Json -Depth 20 -Compress))) 'Legacy/v1 retrieval behavior differs.'
    $oldRoute = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$HostPort/api/chat" -ContentType 'application/json' -Body $body
    $newRoute = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$HostPort/api/v1/chat" -ContentType 'application/json' -Body $body
    Assert-True (($oldRoute | ConvertTo-Json -Depth 20 -Compress) -eq ($newRoute | ConvertTo-Json -Depth 20 -Compress)) 'Legacy/v1 chat behavior differs.'
    Assert-True ((Get-Web '/api/v1/documents/Toy_QC_order.pdf').StatusCode -eq 200) 'Registered PDF did not succeed.'
    foreach ($bad in @('../Toy_QC_order.pdf', '%2e%2e%2fToy_QC_order.pdf', 'unknown.pdf')) {
        try { Get-Web "/api/v1/documents/$bad"; throw 'Invalid document unexpectedly succeeded.' } catch { Assert-True ($_.Exception.Response.StatusCode.value__ -eq 404) 'Invalid document did not fail safely.' }
    }
    try { Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$HostPort/api/v1/chat" -ContentType 'application/json' -Body '{"question":"Tell me about BIS toy regulation"}'; throw 'Provider request unexpectedly succeeded.' } catch { Assert-True ($_.Exception.Response.StatusCode.value__ -eq 503) 'Provider-free request was not safely rejected.' }
    Assert-True ((docker exec $Name id -u) -eq '10001') 'Container does not run as the non-root application user.'
    $retrievalProviderEntries = 0
    $localRetrieverEntries = 0
    $llmProviderEntries = 0
    $disabledProviderEntries = 0
    $nonEmptyGroqEntries = 0
    $nonEmptyLlmEntries = 0
    foreach ($target in @($Name, $Image)) {
        $environmentEntries = @(docker inspect $target --format '{{json .Config.Env}}' | ConvertFrom-Json)
        foreach ($environmentEntry in $environmentEntries) {
            if ($target -eq $Name -and $environmentEntry -is [string] -and $environmentEntry.StartsWith('RETRIEVAL_PROVIDER=', [System.StringComparison]::Ordinal)) {
                $retrievalProviderEntries++
                if ($environmentEntry -ceq 'RETRIEVAL_PROVIDER=chroma_local') { $localRetrieverEntries++ }
            }
            if ($target -eq $Name -and $environmentEntry -is [string] -and $environmentEntry.StartsWith('LLM_PROVIDER=', [System.StringComparison]::Ordinal)) {
                $llmProviderEntries++
            }
            if ($target -eq $Name -and $environmentEntry -ceq 'LLM_PROVIDER=disabled') {
                $disabledProviderEntries++
            }
            if ($environmentEntry -is [string] -and $environmentEntry.StartsWith('GROQ_API_KEY=', [System.StringComparison]::Ordinal)) {
                $groqValue = $environmentEntry.Substring('GROQ_API_KEY='.Length)
                if ($groqValue.Length -gt 0) { $nonEmptyGroqEntries++ }
            }
            if ($environmentEntry -is [string] -and $environmentEntry.StartsWith('LLM_API_KEY=', [System.StringComparison]::Ordinal)) {
                $llmValue = $environmentEntry.Substring('LLM_API_KEY='.Length)
                if ($llmValue.Length -gt 0) { $nonEmptyLlmEntries++ }
            }
        }
    }
    Assert-True ([bool]($retrievalProviderEntries -eq 1 -and $localRetrieverEntries -eq 1)) 'Container does not have exactly one local Chroma retrieval provider entry.'
    Assert-True ([bool]($llmProviderEntries -eq 1 -and $disabledProviderEntries -eq 1)) 'Container does not have exactly one disabled LLM provider entry.'
    Assert-True ([bool]($nonEmptyGroqEntries -eq 0)) 'A non-empty GROQ_API_KEY was configured.'
    Assert-True ([bool]($nonEmptyLlmEntries -eq 0)) 'A non-empty LLM_API_KEY was configured.'
    $historyGroqMatches = @(docker history --no-trunc $Image | Select-String -Pattern 'GROQ_API_KEY=')
    Assert-True ([bool]($historyGroqMatches.Count -eq 0)) 'Image history references GROQ_API_KEY.'
    $historyLlmMatches = @(docker history --no-trunc $Image | Select-String -Pattern 'LLM_API_KEY=')
    Assert-True ([bool]($historyLlmMatches.Count -eq 0)) 'Image history references LLM_API_KEY.'
    docker restart $Name | Out-Null
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds); do { Start-Sleep -Seconds 2; $health = docker inspect --format '{{.State.Health.Status}}' $Name } while ($health -ne 'healthy' -and (Get-Date) -lt $deadline)
    Assert-True ($health -eq 'healthy' -and (Get-Json '/api/v1/health').collection_count -eq 917) 'Restart acceptance failed.'
    docker stop --timeout 20 $Name | Out-Null
    Assert-True ((docker inspect --format '{{.State.Running}}' $Name) -eq 'false') 'SIGTERM/docker stop did not complete.'
    Write-Host 'Container acceptance passed.'
}
finally {
    Remove-Item Env:GROQ_API_KEY -ErrorAction SilentlyContinue
    Stop-TestContainer
}
