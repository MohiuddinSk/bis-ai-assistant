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

    def test_manual_container_acceptance_is_isolated_and_read_only(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        self.assertIn("[CmdletBinding()]", script)
        self.assertIn("$PSScriptRoot", script)
        self.assertIn("$ExpectedCollectionCount = 917", script)
        self.assertIn("$Image = \"bis-saarthi-backend:acceptance-$PID\"", script)
        self.assertIn("$ContainerId", script)
        self.assertIn("Get-ProtectedHashes $ProtectedDirectories", script)
        self.assertIn("Assert-HashesUnchanged $BeforeHashes $AfterHashes", script)
        self.assertIn("Assert-ProtectedGitClean", script)
        self.assertIn("finally {", script)
        self.assertIn("Stop-TestContainer", script)
        for marker in (
            "data/raw", "data/processed", "evaluation", "data/chroma",
            "RETRIEVAL_PROVIDER=chroma_local", "LLM_PROVIDER=disabled", "GROQ_API_KEY=", "LLM_API_KEY=",
            "HF_HUB_OFFLINE=1", "TRANSFORMERS_OFFLINE=1", "id -u", "id -g",
            "/health", "/api/v1/health", "/api/retrieve", "/api/v1/retrieve", "/api/chat", "/api/v1/chat",
        ):
            self.assertIn(marker, script)
        for forbidden in ("docker volume", "docker system", "docker image rm", "docker logs", "Remove-Item", "git reset", "git checkout", "git clean"):
            self.assertNotIn(forbidden.lower(), script.lower())

    def test_manual_acceptance_checks_legacy_and_versioned_routes(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        for path in ("/health", "/api/v1/health", "/api/retrieve", "/api/v1/retrieve", "/api/chat", "/api/v1/chat"):
            self.assertIn(path, script)
        self.assertIn("$LegacyRetrieve", script)
        self.assertIn("$VersionedRetrieve", script)
        self.assertIn("$LegacyChat", script)
        self.assertIn("$VersionedChat", script)

    def test_manual_acceptance_requires_local_retrieval_provider(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        self.assertIn("-e RETRIEVAL_PROVIDER=chroma_local", script)
        self.assertIn('"RETRIEVAL_PROVIDER=chroma_local"', script)
        self.assertIn('"RETRIEVAL_PROVIDER"', script)

    def test_manual_acceptance_disables_generation_and_empties_keys(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        for marker in ("-e LLM_PROVIDER=disabled", "-e GROQ_API_KEY=", "-e LLM_API_KEY=", '"LLM_PROVIDER=disabled"', '"GROQ_API_KEY="', '"LLM_API_KEY="'):
            self.assertIn(marker, script)

    def test_manual_acceptance_rejects_missing_duplicate_and_conflicting_environment_entries(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        self.assertIn("$NamedEntries.Count -eq 1", script)
        self.assertIn("StartsWith(\"$EnvironmentName=\"", script)
        self.assertIn("$RequiredEntry", script)

    def test_manual_acceptance_parses_docker_environment_without_printing_secrets(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        self.assertIn("docker inspect $ContainerId --format '{{json .Config.Env}}'", script)
        self.assertIn("ConvertFrom-Json", script)
        self.assertIn("$Entry.EndsWith(\"=\")", script)
        self.assertNotIn("Write-Output $EnvironmentEntries", script)
        self.assertNotIn("Write-Output $Entry", script)

    def test_manual_acceptance_handles_request_id_headers_as_a_collection(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        self.assertIn('$ResponseRequestIds = @($HealthResponse.Headers["X-Request-ID"])', script)
        self.assertIn("$ResponseRequestIds.Count -eq 1", script)
        self.assertIn("[string]$ResponseRequestIds[0] -ceq $RequestId", script)

    def test_manual_acceptance_checks_every_expected_endpoint_path(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        for path in ("/api/v1/compliance/guide", "/api/v1/documents/Toy_QC_order.pdf", "/health", "/api/v1/health", "/api/retrieve", "/api/v1/retrieve", "/api/chat", "/api/v1/chat"):
            self.assertIn(path, script)

    def test_manual_acceptance_constructs_hashed_paths_from_the_repository_root(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        self.assertIn("$_.FullName.Substring($Root.Length).TrimStart('\\').Replace('\\', '/')", script)
        self.assertIn("Get-ChildItem -LiteralPath $Directory -File -Recurse -Force", script)
        self.assertIn("git -C $Root status --porcelain=v1 --untracked-files=all -- data/raw data/processed evaluation", script)

    def test_manual_acceptance_cleanup_targets_only_its_container(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        self.assertIn("$ActualName = docker inspect --format '{{.Name}}' $ContainerId", script)
        self.assertIn('$ActualName -eq "/$Name"', script)
        self.assertIn("docker rm -f $ContainerId", script)
        self.assertNotIn("docker rm -f $Name", script)

    def test_manual_acceptance_never_deletes_images_or_volumes(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8").lower()
        for forbidden in ("docker image rm", "docker rmi", "docker volume rm", "docker volume prune", "docker system prune"):
            self.assertNotIn(forbidden, script)

    def test_manual_acceptance_verifies_hashes_after_a_failed_test_path(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        finally_block = script.split("finally {", 1)[1]
        self.assertIn("$AfterHashes = Get-ProtectedHashes $ProtectedDirectories", finally_block)
        self.assertIn("Assert-HashesUnchanged $BeforeHashes $AfterHashes", finally_block)
        self.assertIn("Assert-ProtectedGitClean", finally_block)

    def test_manual_acceptance_restores_environment_in_finally(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        finally_block = script.split("finally {", 1)[1]
        self.assertIn("[Environment]::SetEnvironmentVariable($EnvironmentName, $OriginalEnvironment[$EnvironmentName], \"Process\")", finally_block)
        self.assertNotIn("Remove-Item Env:", script)

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
