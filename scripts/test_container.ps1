[CmdletBinding()]
param(
    [int]$TimeoutSeconds = 180,
    [int]$HostPort = 18000,
    [int]$ExpectedCollectionCount = 917
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$Image = "bis-saarthi-backend:acceptance-$PID"
$Name = "bis-saarthi-container-test-$PID"
$ContainerId = $null
$ProtectedDirectories = @("data/raw", "data/processed", "evaluation", "data/chroma")
$EnvironmentNames = @("GROQ_API_KEY", "LLM_API_KEY", "RETRIEVAL_PROVIDER", "LLM_PROVIDER", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
$OriginalEnvironment = @{}
foreach ($EnvironmentName in $EnvironmentNames) {
    $OriginalEnvironment[$EnvironmentName] = [Environment]::GetEnvironmentVariable($EnvironmentName, "Process")
}

function Assert-Condition {
    param([bool]$Condition)
    if (-not $Condition) { throw "Container acceptance validation failed." }
}

function Assert-Prerequisite {
    param([bool]$Condition, [string]$Reason)
    if (-not $Condition) {
        $script:PrerequisiteFailureReason = $Reason
        throw "Container acceptance prerequisite failed."
    }
}

function Get-ProtectedHashes {
    param([string[]]$Directories)
    $Hashes = @{}
    foreach ($RelativeDirectory in $Directories) {
        $Directory = Join-Path $Root $RelativeDirectory
        Assert-Condition (Test-Path -LiteralPath $Directory -PathType Container)
        Get-ChildItem -LiteralPath $Directory -File -Recurse -Force | ForEach-Object {
            $RelativePath = $_.FullName.Substring($Root.Length).TrimStart('\').Replace('\', '/')
            $Hashes[$RelativePath] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        }
    }
    return $Hashes
}

function Assert-HashesUnchanged {
    param([hashtable]$Before, [hashtable]$After)
    Assert-Condition ($Before.Count -eq $After.Count)
    foreach ($Path in $Before.Keys) {
        Assert-Condition ($After.ContainsKey($Path))
        Assert-Condition ($Before[$Path] -eq $After[$Path])
    }
    foreach ($Path in $After.Keys) { Assert-Condition ($Before.ContainsKey($Path)) }
}

function Assert-ProtectedGitClean {
    param([switch]$Prerequisite)
    $Status = @(git -C $Root status --porcelain=v1 --untracked-files=all -- data/raw data/processed data/chroma evaluation 2>$null)
    if ($Prerequisite) {
        Assert-Prerequisite ($LASTEXITCODE -eq 0) "protected-path-status-unavailable"
        Assert-Prerequisite ($Status.Count -eq 0) "protected-paths-dirty"
        return
    }
    Assert-Condition ($LASTEXITCODE -eq 0)
    Assert-Condition ($Status.Count -eq 0)
}

function Invoke-ApiJson {
    param([string]$Path, [string]$Method = "GET", [string]$Body = $null, [hashtable]$Headers = @{})
    $Parameters = @{ Uri = "http://127.0.0.1:$HostPort$Path"; Method = $Method; Headers = $Headers; TimeoutSec = 10 }
    if ($null -ne $Body) { $Parameters["ContentType"] = "application/json"; $Parameters["Body"] = $Body }
    return Invoke-RestMethod @Parameters
}

function Stop-TestContainer {
    if ($null -eq $ContainerId) { return }
    $ActualName = docker inspect --format '{{.Name}}' $ContainerId 2>$null
    if ($LASTEXITCODE -eq 0 -and $ActualName -eq "/$Name") {
        docker rm -f $ContainerId 2>$null | Out-Null
    }
}

$Succeeded = $false
$BeforeHashes = $null
$PrerequisitesComplete = $false
$PrerequisiteFailureReason = "unknown-prerequisite"
try {
    Write-Output "Validating container acceptance prerequisites."
    docker version --format '{{.Server.Version}}' 2>$null | Out-Null
    Assert-Prerequisite ($LASTEXITCODE -eq 0) "docker-daemon-unavailable"
    Assert-Prerequisite ($TimeoutSeconds -gt 0 -and $HostPort -gt 0 -and $HostPort -le 65535) "invalid-acceptance-parameters"
    Assert-Prerequisite (Test-Path -LiteralPath (Join-Path $Root "data/chroma") -PathType Container) "chroma-index-directory-missing"
    foreach ($RequiredArtifact in @(
        "data/processed/generated_v3/embedding_manifest.json",
        "data/processed/generated_v3/source_registry.json",
        "data/processed/generated_v3/chunks.jsonl"
    )) {
        Assert-Prerequisite (Test-Path -LiteralPath (Join-Path $Root $RequiredArtifact) -PathType Leaf) "required-index-artifact-missing"
    }
    Assert-ProtectedGitClean -Prerequisite
    $BeforeHashes = Get-ProtectedHashes $ProtectedDirectories
    $PortInUse = Get-NetTCPConnection -LocalPort $HostPort -State Listen -ErrorAction SilentlyContinue
    Assert-Prerequisite ($null -eq $PortInUse) "acceptance-host-port-in-use"
    $PrerequisitesComplete = $true

    [Environment]::SetEnvironmentVariable("GROQ_API_KEY", "", "Process")
    [Environment]::SetEnvironmentVariable("LLM_API_KEY", "", "Process")
    [Environment]::SetEnvironmentVariable("RETRIEVAL_PROVIDER", "chroma_local", "Process")
    [Environment]::SetEnvironmentVariable("LLM_PROVIDER", "disabled", "Process")
    [Environment]::SetEnvironmentVariable("HF_HUB_OFFLINE", "1", "Process")
    [Environment]::SetEnvironmentVariable("TRANSFORMERS_OFFLINE", "1", "Process")

    Write-Output "Building manual acceptance image."
    docker build --tag $Image $Root 2>$null | Out-Null
    Assert-Condition ($LASTEXITCODE -eq 0)

    Write-Output "Starting manual acceptance container."
    $ContainerId = docker run --detach --name $Name --init --cap-drop ALL --security-opt no-new-privileges:true --tmpfs /tmp:rw,nosuid,nodev,size=64m -p "${HostPort}:8000" -e RETRIEVAL_PROVIDER=chroma_local -e LLM_PROVIDER=disabled -e GROQ_API_KEY= -e LLM_API_KEY= -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 $Image 2>$null
    Assert-Condition ($LASTEXITCODE -eq 0 -and $ContainerId -is [string] -and $ContainerId.Length -gt 0)

    Write-Output "Waiting for container health."
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $Health = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' $ContainerId 2>$null
        if ($Health -eq "healthy") { break }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $Deadline)
    Assert-Condition ($Health -eq "healthy")
    Assert-Condition ((docker inspect --format '{{.State.Running}}' $ContainerId 2>$null) -eq "true")

    Write-Output "Checking container routes and runtime contract."
    $LegacyHealth = Invoke-ApiJson "/health"
    $VersionedHealth = Invoke-ApiJson "/api/v1/health"
    Assert-Condition ($LegacyHealth.status -eq "ready" -and $VersionedHealth.status -eq "ready")
    Assert-Condition ($LegacyHealth.collection_count -eq $ExpectedCollectionCount -and $VersionedHealth.collection_count -eq $ExpectedCollectionCount)
    $RequestId = "container-test-request-001"
    $HealthResponse = Invoke-WebRequest -Uri "http://127.0.0.1:$HostPort/api/v1/health" -Headers @{ "X-Request-ID" = $RequestId } -TimeoutSec 10
    $ResponseRequestIds = @($HealthResponse.Headers["X-Request-ID"])
    Assert-Condition ($ResponseRequestIds.Count -eq 1 -and $ResponseRequestIds[0] -is [string] -and [string]$ResponseRequestIds[0] -ceq $RequestId)

    $RetrievalBody = '{"question":"what standards apply to a battery-operated toy"}'
    $LegacyRetrieve = Invoke-ApiJson "/api/retrieve" "POST" $RetrievalBody
    $VersionedRetrieve = Invoke-ApiJson "/api/v1/retrieve" "POST" $RetrievalBody
    Assert-Condition ($LegacyRetrieve.result_count -gt 0)
    Assert-Condition (($LegacyRetrieve | ConvertTo-Json -Depth 20 -Compress) -eq ($VersionedRetrieve | ConvertTo-Json -Depth 20 -Compress))
    $LegacyChat = Invoke-ApiJson "/api/chat" "POST" $RetrievalBody
    $VersionedChat = Invoke-ApiJson "/api/v1/chat" "POST" $RetrievalBody
    Assert-Condition (($LegacyChat | ConvertTo-Json -Depth 20 -Compress) -eq ($VersionedChat | ConvertTo-Json -Depth 20 -Compress))
    $Clarification = Invoke-ApiJson "/api/v1/chat" "POST" '{"question":"what standards apply to toys"}'
    Assert-Condition ($Clarification.needs_clarification -and $Clarification.generation_mode -eq "clarification")
    $Profile = '{"role":"manufacturer","product_description":"Battery-operated toy car","power_type":"battery_operated","intended_age_group":"3_to_8","goal":"identify_standards","application_stage":"researching","additional_context":null}'
    $Guide = Invoke-ApiJson "/api/v1/compliance/guide" "POST" $Profile
    Assert-Condition ($Guide.guidance.grounded -and $Guide.guidance.answer -match "IS 15644")
    Assert-Condition ((Invoke-WebRequest -Uri "http://127.0.0.1:$HostPort/api/v1/documents/Toy_QC_order.pdf" -TimeoutSec 10).StatusCode -eq 200)

    try { Invoke-ApiJson "/api/v1/chat" "POST" '{"question":"Tell me about BIS toy regulation"}'; throw "Container acceptance validation failed." }
    catch { Assert-Condition ($_.Exception.Response.StatusCode.value__ -eq 503) }
    Assert-Condition ((docker exec $ContainerId id -u 2>$null) -eq "10001")
    Assert-Condition ((docker exec $ContainerId id -g 2>$null) -eq "10001")

    $EnvironmentEntries = @(docker inspect $ContainerId --format '{{json .Config.Env}}' 2>$null | ConvertFrom-Json)
    $RequiredEnvironment = @("RETRIEVAL_PROVIDER=chroma_local", "LLM_PROVIDER=disabled", "GROQ_API_KEY=", "LLM_API_KEY=")
    foreach ($RequiredEntry in $RequiredEnvironment) { Assert-Condition (($EnvironmentEntries | Where-Object { $_ -ceq $RequiredEntry }).Count -eq 1) }
    foreach ($EnvironmentName in @("RETRIEVAL_PROVIDER", "LLM_PROVIDER", "GROQ_API_KEY", "LLM_API_KEY")) {
        $NamedEntries = @($EnvironmentEntries | Where-Object { $_ -is [string] -and $_.StartsWith("$EnvironmentName=", [System.StringComparison]::Ordinal) })
        Assert-Condition ($NamedEntries.Count -eq 1)
    }
    foreach ($Entry in $EnvironmentEntries) {
        if ($Entry -is [string] -and ($Entry.StartsWith("GROQ_API_KEY=", [System.StringComparison]::Ordinal) -or $Entry.StartsWith("LLM_API_KEY=", [System.StringComparison]::Ordinal))) {
            Assert-Condition ($Entry.EndsWith("="))
        }
    }
    Assert-Condition (@(docker history --no-trunc $Image 2>$null | Select-String -Pattern "GROQ_API_KEY=|LLM_API_KEY=").Count -eq 0)

    $Succeeded = $true
}
catch {
    if (-not $PrerequisitesComplete) {
        Write-Output "Manual container acceptance prerequisite failed: $PrerequisiteFailureReason"
    }
    else {
        Write-Output "Manual container acceptance failed."
    }
}
finally {
    if ($null -ne $BeforeHashes) {
        Write-Output "Verifying protected artifacts."
        try {
            $AfterHashes = Get-ProtectedHashes $ProtectedDirectories
            Assert-HashesUnchanged $BeforeHashes $AfterHashes
            Assert-ProtectedGitClean
        }
        catch {
            $Succeeded = $false
        }
    }
    Stop-TestContainer
    foreach ($EnvironmentName in $EnvironmentNames) {
        [Environment]::SetEnvironmentVariable($EnvironmentName, $OriginalEnvironment[$EnvironmentName], "Process")
    }
}

if (-not $Succeeded) { exit 1 }
Write-Output "Manual container acceptance passed."
