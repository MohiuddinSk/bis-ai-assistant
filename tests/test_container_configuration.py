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
        self.assertIn("$_.Path -notin $Allowed", script)
        self.assertIn("$status -match '[RD]'", script)
        for path in ("scripts/container_healthcheck.py", "scripts/test_container.ps1"):
            self.assertIn(path, script)

    def test_acceptance_allowlist_includes_only_gateway_task_files(self):
        script = (ROOT / "scripts/test_container.ps1").read_text(encoding="utf-8")
        for path in ("backend/generation_factory.py", "backend/openai_compatible_generator.py", "tests/test_generation_factory.py", "tests/test_provider_disabled_api.py"):
            self.assertIn(path, script)
        allowlist = script.split("$Allowed = @(", 1)[1].split(")", 1)[0]
        self.assertEqual(allowlist.count("'tests/test_provider_disabled_api.py'"), 1)
        self.assertNotIn("'backend/'", allowlist)
        self.assertNotIn("*", allowlist)

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

    def test_healthcheck_and_versioned_paths_are_preserved(self):
        health = (ROOT / "scripts/container_healthcheck.py").read_text(encoding="utf-8")
        main = (ROOT / "backend/main.py").read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:8000/api/v1/health", health)
        self.assertNotIn("917", health)
        for path in ("/health", "/api/v1/health", "/api/chat", "/api/v1/chat", "/api/documents/{source_filename}", "/api/v1/documents/{source_filename}"):
            self.assertIn(path, main)


if __name__ == "__main__":
    unittest.main()
