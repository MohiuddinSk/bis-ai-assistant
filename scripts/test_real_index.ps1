[CmdletBinding()]
param(
    [string]$PythonPath = (Join-Path (Split-Path -Parent $PSScriptRoot) "venv311\Scripts\python.exe"),
    [int]$ExpectedCollectionCount = 917
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$ProtectedDirectories = @("data/raw", "data/processed", "evaluation", "data/chroma")
$EnvironmentNames = @(
    "RETRIEVAL_PROVIDER", "LLM_PROVIDER", "GROQ_API_KEY", "LLM_API_KEY",
    "TRANSFORMERS_OFFLINE", "HF_HUB_OFFLINE"
)
$OriginalEnvironment = @{}
foreach ($Name in $EnvironmentNames) {
    $OriginalEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
}

function Assert-Condition {
    param([bool]$Condition)
    if (-not $Condition) {
        throw "Read-only acceptance validation failed."
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

function Assert-ProtectedGitClean {
    $Status = @(git -C $Root status --porcelain=v1 --untracked-files=all -- data/raw data/processed evaluation 2>$null)
    Assert-Condition ($LASTEXITCODE -eq 0)
    Assert-Condition ($Status.Count -eq 0)
}

function Assert-HashesUnchanged {
    param(
        [hashtable]$Before,
        [hashtable]$After
    )

    Assert-Condition ($Before.Count -eq $After.Count)
    foreach ($Path in $Before.Keys) {
        Assert-Condition ($After.ContainsKey($Path))
        Assert-Condition ($Before[$Path] -eq $After[$Path])
    }
    foreach ($Path in $After.Keys) {
        Assert-Condition ($Before.ContainsKey($Path))
    }
}

$Succeeded = $false
$HasTestFailure = $false
$ReportedTestFailure = $false
try {
    Write-Output "Validating read-only prerequisites."
    Assert-Condition (Test-Path -LiteralPath $PythonPath -PathType Leaf)
    & $PythonPath -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" 2>$null | Out-Null
    Assert-Condition ($LASTEXITCODE -eq 0)
    Assert-Condition (Test-Path -LiteralPath (Join-Path $Root "data/chroma") -PathType Container)
    foreach ($RequiredArtifact in @(
        "data/processed/generated_v3/embedding_manifest.json",
        "data/processed/generated_v3/source_registry.json",
        "data/processed/generated_v3/chunks.jsonl"
    )) {
        Assert-Condition (Test-Path -LiteralPath (Join-Path $Root $RequiredArtifact) -PathType Leaf)
    }
    Assert-ProtectedGitClean
    $BeforeHashes = Get-ProtectedHashes $ProtectedDirectories

    [Environment]::SetEnvironmentVariable("RETRIEVAL_PROVIDER", "chroma_local", "Process")
    [Environment]::SetEnvironmentVariable("LLM_PROVIDER", "disabled", "Process")
    [Environment]::SetEnvironmentVariable("GROQ_API_KEY", "", "Process")
    [Environment]::SetEnvironmentVariable("LLM_API_KEY", "", "Process")
    [Environment]::SetEnvironmentVariable("TRANSFORMERS_OFFLINE", "1", "Process")
    [Environment]::SetEnvironmentVariable("HF_HUB_OFFLINE", "1", "Process")

    Write-Output "Checking committed artifacts."
    & $PythonPath (Join-Path $Root "scripts/check_ci_artifacts.py") 2>$null | Out-Null
    Assert-Condition ($LASTEXITCODE -eq 0)

    Write-Output "Running local retrieval smoke check."
    $SmokeCheck = @'
import math
import sys
from collections.abc import Mapping
from backend.retrieval_factory import create_retrieval_provider
from backend.retrieval_provider import LocalChromaRetriever, RetrievalHit

provider = create_retrieval_provider()
if type(provider) is not LocalChromaRetriever:
    raise RuntimeError()
if provider.count() != int(sys.argv[1]):
    raise RuntimeError()
hits = provider.search("Which standard applies to a battery-operated toy?", k=5)
if len(hits) != 5:
    raise RuntimeError()
for hit in hits:
    if not isinstance(hit, RetrievalHit):
        raise RuntimeError()
    if not isinstance(hit.chunk_id, str) or not hit.chunk_id.strip():
        raise RuntimeError()
    if not isinstance(hit.text, str) or not hit.text.strip():
        raise RuntimeError()
    if not isinstance(hit.metadata, Mapping):
        raise RuntimeError()
    if not isinstance(hit.distance, (int, float)) or not math.isfinite(hit.distance):
        raise RuntimeError()
'@
    & $PythonPath -c $SmokeCheck $ExpectedCollectionCount 2>$null | Out-Null
    Assert-Condition ($LASTEXITCODE -eq 0)

    Write-Output "Running real-index acceptance tests."
    $RealIndexTargets = @(
        "tests.test_compliance_real_data_integration",
        "tests.test_question_understanding_real_data",
        "tests.test_real_data_integration",
        "tests.test_standard_explanation.StandardExplanationRealIndexTests"
    )
    foreach ($Target in $RealIndexTargets) {
        & $PythonPath -m unittest -v $Target 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Output "Real-index test failed: $Target"
            $HasTestFailure = $true
            $ReportedTestFailure = $true
        }
    }

    Write-Output "Verifying protected artifacts."
    $AfterHashes = Get-ProtectedHashes $ProtectedDirectories
    Assert-HashesUnchanged $BeforeHashes $AfterHashes
    Assert-ProtectedGitClean
    $Succeeded = -not $HasTestFailure
}
catch {
    if (-not $ReportedTestFailure) {
        Write-Output "Read-only real-index acceptance failed."
    }
    $Succeeded = $false
}
finally {
    foreach ($Name in $EnvironmentNames) {
        [Environment]::SetEnvironmentVariable($Name, $OriginalEnvironment[$Name], "Process")
    }
}

if (-not $Succeeded) {
    exit 1
}

Write-Output "Read-only real-index acceptance passed."
