"""Static guardrails for the prototype container; does not build an image."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ContainerConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    def test_required_files_exist(self):
        for relative in (
            "Dockerfile", ".dockerignore", "compose.yaml",
            "scripts/container_healthcheck.py", "scripts/test_container.ps1",
            "docs/CONTAINER_DEPLOYMENT.md",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_dockerfile_runtime_contract(self):
        self.assertRegex(self.dockerfile, r"(?mi)^FROM python:3\.11\.\d+-slim-bookworm$")
        self.assertIn("WORKDIR /app", self.dockerfile)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", self.dockerfile)
        self.assertIn("PYTHONUNBUFFERED=1", self.dockerfile)
        self.assertIn("HF_HUB_OFFLINE=1", self.dockerfile)
        self.assertIn("TRANSFORMERS_OFFLINE=1", self.dockerfile)
        self.assertIn("614241f622f53c4eeff9890bdc4f31cfecc418b3", self.dockerfile)
        self.assertIn("USER 10001:10001", self.dockerfile)
        self.assertIn("EXPOSE 8000", self.dockerfile)
        self.assertRegex(self.dockerfile, r"HEALTHCHECK[\s\S]*container_healthcheck\.py")
        self.assertIn('CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]', self.dockerfile)
        self.assertNotRegex(self.dockerfile, r"(?im)^\s*(ARG|ENV)\s+[^\n]*GROQ_API_KEY\s*=\s*[^\s$]+")

    def test_only_runtime_directories_are_copied(self):
        for path in ("backend", "retrieval", "data/raw", "data/processed/generated_v3", "data/chroma"):
            self.assertRegex(self.dockerfile, rf"(?m)^COPY {re.escape(path)}(?:\s|$)")
        for forbidden in ("frontend", "tests", "ingestion", "evaluation", ".git", "venv"):
            self.assertNotRegex(self.dockerfile, rf"(?m)^COPY {re.escape(forbidden)}(?:\s|$)")

    def test_ignore_and_compose_security_guardrails(self):
        for entry in (".git", "frontend", "ingestion", "tests", "evaluation", ".env", "credentials", "data/processed/generated_v2"):
            self.assertIn(entry, self.ignore)
        self.assertIn("RETRIEVAL_PROVIDER: ${RETRIEVAL_PROVIDER:-chroma_local}", self.compose)
        self.assertIn("GROQ_API_KEY: ${GROQ_API_KEY:-}", self.compose)
        self.assertIn("ALLOWED_ORIGINS:", self.compose)
        self.assertIn("cap_drop:", self.compose)
        self.assertIn("no-new-privileges:true", self.compose)
        self.assertNotRegex(self.compose, r"(?im)^\s*privileged\s*:\s*true")
        self.assertNotIn("/var/run/docker.sock", self.compose)
        self.assertNotRegex(self.compose, r"(?m)^\s*-\s*\.:/app")

    def test_acceptance_status_check_enumerates_exact_paths(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        self.assertIn("git -C $Root status --porcelain=v1 --untracked-files=all", script)
        self.assertIn("$path = $line.Substring(3).Replace('\\', '/')", script)
        self.assertIn("[pscustomobject]@{ Status = $status; Path = $path }", script)
        self.assertIn("$_.Path -notin $Allowed", script)
        self.assertIn("$status -match '[RD]'", script)
        self.assertIn("Assert-True ($unexpected.Count -eq 0)", script)
        allowlist = script.split("$Allowed = @(", 1)[1].split(")", 1)[0]
        self.assertNotIn("scripts/container_healthcheck.py", allowlist)

    def test_acceptance_allowlist_matches_retrieval_abstraction_task_files(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        allowlist = script.split("$Allowed = @(", 1)[1].split(")", 1)[0]
        expected = (
            "backend/chat_service.py", "backend/main.py", "backend/service.py", "backend/settings.py",
            "backend/retrieval_factory.py", "backend/retrieval_provider.py", "compose.yaml",
            "docs/BIS_INTEGRATION_READINESS.md", "docs/CONTAINER_DEPLOYMENT.md",
            "scripts/test_container.ps1", "tests/test_api.py", "tests/test_chat_api.py",
            "tests/test_container_configuration.py", "tests/test_retrieval_disabled_api.py",
            "tests/test_retrieval_factory.py", "tests/test_retrieval_provider_contract.py",
        )
        for path in expected:
            self.assertEqual(allowlist.count(f"'{path}'"), 1)
        self.assertNotIn("'backend/'", allowlist)
        self.assertNotIn("*", allowlist)
        self.assertNotIn("backend/generation_factory.py", allowlist)
        self.assertNotIn("tests/test_provider_disabled_api.py", allowlist)

    def test_acceptance_unexpected_paths_are_joined_from_path_values(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        self.assertIn("$unexpectedPaths = @(", script)
        self.assertIn("ForEach-Object { $_.Path }", script)
        self.assertIn("$unexpectedPaths -join ', '", script)
        self.assertIn("$unexpected.Count -eq 0", script)
        self.assertNotIn("$unexpected -join ', '", script)

    def test_acceptance_request_id_check_handles_header_collections(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        self.assertIn("$responseRequestIds = @($response.Headers['X-Request-ID'])", script)
        self.assertIn("$responseRequestIds.Count -eq 1", script)
        self.assertIn("$responseRequestIds[0] -is [string]", script)
        self.assertIn("[string]$responseRequestIds[0] -ceq $requestId", script)
        self.assertIn("Assert-True ([bool]$requestIdWasPreserved)", script)

    def test_acceptance_secret_check_parses_environment_arrays(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        self.assertIn("docker inspect $target --format '{{json .Config.Env}}' | ConvertFrom-Json", script)
        self.assertIn("StartsWith('GROQ_API_KEY=', [System.StringComparison]::Ordinal)", script)
        self.assertIn("Substring('GROQ_API_KEY='.Length)", script)
        self.assertIn("$groqValue.Length -gt 0", script)
        self.assertIn("$nonEmptyGroqEntries -eq 0", script)
        self.assertNotIn("Write-Host $groqValue", script)
        self.assertNotIn("Write-Output $groqValue", script)
        self.assertIn("$historyGroqMatches = @(docker history", script)
        self.assertNotIn("Select-String -Pattern 'GROQ_API_KEY=.+'", script)
        self.assertIn("$historyLlmMatches = @(docker history", script)
        self.assertNotIn("Select-String -Pattern 'LLM_API_KEY=.+'", script)
        self.assertIn("docker stop --timeout 20", script)
        self.assertNotIn("docker stop --time 20", script)

    def test_acceptance_container_runs_with_disabled_provider_and_empty_runtime_keys(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        run_command = script.split("docker run --detach", 1)[1].split("| Out-Null", 1)[0]
        self.assertIn("-e LLM_PROVIDER=disabled", run_command)
        self.assertIn("-e GROQ_API_KEY=", run_command)
        self.assertIn("-e LLM_API_KEY=", run_command)
        self.assertNotIn("LLM_BASE_URL", run_command)
        self.assertNotIn("LLM_MODEL", run_command)
        self.assertNotIn("LLM_ALLOWED_HOSTS", run_command)
        self.assertIn("$disabledProviderEntries -eq 1", script)
        self.assertIn("$nonEmptyLlmEntries -eq 0", script)
        self.assertNotIn("Write-Host $llmValue", script)
        self.assertNotIn("Write-Output $llmValue", script)

    def test_acceptance_container_runs_with_exact_local_retrieval_provider(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        run_command = script.split("docker run --detach", 1)[1].split("| Out-Null", 1)[0]
        self.assertIn("-e RETRIEVAL_PROVIDER=chroma_local", run_command)
        self.assertIn("$retrievalProviderEntries -eq 1 -and $localRetrieverEntries -eq 1", script)
        self.assertIn("StartsWith('RETRIEVAL_PROVIDER=', [System.StringComparison]::Ordinal)", script)
        self.assertIn("$llmProviderEntries -eq 1 -and $disabledProviderEntries -eq 1", script)

    def test_acceptance_provider_environment_checks_reject_missing_duplicate_and_conflicting_entries(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        self.assertIn("$retrievalProviderEntries++", script)
        self.assertIn("$localRetrieverEntries++", script)
        self.assertIn("$retrievalProviderEntries -eq 1 -and $localRetrieverEntries -eq 1", script)
        self.assertIn("$llmProviderEntries++", script)
        self.assertIn("$llmProviderEntries -eq 1 -and $disabledProviderEntries -eq 1", script)

    def test_acceptance_checks_legacy_and_versioned_retrieval_routes(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        self.assertIn("/api/retrieve", script)
        self.assertIn("/api/v1/retrieve", script)
        self.assertIn("Legacy/v1 retrieval behavior differs.", script)

    def test_healthcheck_and_versioned_paths_are_preserved(self):
        health = (ROOT / "scripts/container_healthcheck.py").read_text(encoding="utf-8")
        main = (ROOT / "backend/main.py").read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:8000/api/v1/health", health)
        self.assertNotIn("917", health)
        for path in ("/health", "/api/v1/health", "/api/chat", "/api/v1/chat", "/api/documents/{source_filename}", "/api/v1/documents/{source_filename}"):
            self.assertIn(path, main)

    def test_read_only_real_index_acceptance_contract(self):
        script_path = ROOT / "scripts/test_real_index.ps1"
        self.assertTrue(script_path.is_file())
        script = script_path.read_text(encoding="utf-8")
        self.assertIn("[CmdletBinding()]", script)
        self.assertIn("$PSScriptRoot", script)
        self.assertIn("[int]$ExpectedCollectionCount = 917", script)
        self.assertIn('$ErrorActionPreference = "Stop"', script)
        for marker in (
            '"RETRIEVAL_PROVIDER", "chroma_local", "Process"',
            '"LLM_PROVIDER", "disabled", "Process"',
            '"GROQ_API_KEY", "", "Process"',
            '"LLM_API_KEY", "", "Process"',
            '"TRANSFORMERS_OFFLINE", "1", "Process"',
            '"HF_HUB_OFFLINE", "1", "Process"',
            "scripts/check_ci_artifacts.py",
            "create_retrieval_provider",
            "LocalChromaRetriever, RetrievalHit",
            "provider.count() != int(sys.argv[1])",
            "len(hits) != 5",
            "math.isfinite(hit.distance)",
            "$BeforeHashes = Get-ProtectedHashes $ProtectedDirectories",
            "$AfterHashes = Get-ProtectedHashes $ProtectedDirectories",
            "Assert-HashesUnchanged $BeforeHashes $AfterHashes",
            "$RealIndexTargets = @(",
            "foreach ($Target in $RealIndexTargets)",
            'Write-Output "Real-index test failed: $Target"',
            "$HasTestFailure = $true",
            "finally {",
            "Read-only real-index acceptance passed.",
        ):
            self.assertIn(marker, script)
        expected_targets = (
            "tests.test_compliance_real_data_integration",
            "tests.test_question_understanding_real_data",
            "tests.test_real_data_integration",
            "tests.test_standard_explanation.StandardExplanationRealIndexTests",
        )
        for target in expected_targets:
            self.assertEqual(script.count(target), 1)
        self.assertLess(
            script.index('Write-Output "Real-index test failed: $Target"'),
            script.index("$AfterHashes = Get-ProtectedHashes $ProtectedDirectories"),
        )
        self.assertLess(
            script.index("Assert-HashesUnchanged $BeforeHashes $AfterHashes"),
            script.index("$Succeeded = -not $HasTestFailure"),
        )
        for forbidden in (
            "retrieval/test_retrieval.py", "ingestion/", "build_chroma", "validate_data", "docker",
            "pip install", "remove-item", "git reset", "git checkout", "git clean",
        ):
            self.assertNotIn(forbidden, script.lower())
        self.assertNotIn("Write-Output $OriginalEnvironment", script)
        self.assertNotIn("Write-Output $SmokeCheck", script)

    def test_controlled_evidence_uses_the_provider_neutral_indexed_chunk_contract(self):
        provider = (ROOT / "backend/retrieval_provider.py").read_text(encoding="utf-8")
        service = (ROOT / "backend/chat_service.py").read_text(encoding="utf-8")
        self.assertIn("def indexed_chunks(self) -> Sequence[RetrievalHit]", provider)
        self.assertIn("def adjacent_chunks(", provider)
        self.assertIn("MappingProxyType(dict(metadata))", provider)
        self.assertIn("indexed_chunks = getattr(self._retriever, \"indexed_chunks\", None)", service)
        self.assertIn("rows = indexed_chunks()", service)
        controlled_candidates = service.split("def _controlled_role_candidates", 1)[1].split("def _role_matches", 1)[0]
        self.assertIn("except (TypeError, ValueError):", controlled_candidates)
        self.assertNotIn("except Exception:", controlled_candidates)
        self.assertNotIn("chunks_by_id", controlled_candidates)
        self.assertNotIn("self._retriever.collection", controlled_candidates)


if __name__ == "__main__":
    unittest.main()
