"""Static guardrails for the account-assigned free ngrok demo workflow."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FreeNgrokDemoTests(unittest.TestCase):
    def setUp(self):
        self.start = (ROOT / "deploy/free-ngrok-demo/start.ps1").read_text(encoding="utf-8")
        self.check = (ROOT / "deploy/free-ngrok-demo/check.ps1").read_text(encoding="utf-8")
        self.stop = (ROOT / "deploy/free-ngrok-demo/stop.ps1").read_text(encoding="utf-8")
        self.docs = (ROOT / "docs/FREE_NGROK_DEMO.md").read_text(encoding="utf-8")
        self.ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    def test_required_artifacts_and_isolated_project_exist(self):
        for path in ("deploy/free-ngrok-demo/start.ps1", "deploy/free-ngrok-demo/check.ps1", "deploy/free-ngrok-demo/stop.ps1", "docs/FREE_NGROK_DEMO.md"):
            self.assertTrue((ROOT / path).is_file(), path)
        for content in (self.start, self.check, self.stop):
            self.assertIn('$ProjectName = "free-ngrok-demo"', content)

    def test_assigned_domain_and_narrow_cors_are_required(self):
        self.assertIn('FREE_NGROK_HTTPS_HOSTNAME', self.start)
        self.assertIn('FREE_NGROK_FRONTEND_ORIGIN', self.start)
        self.assertIn('ArgumentList.Add("http")', self.start)
        self.assertIn('ArgumentList.Add("http://127.0.0.1:8000")', self.start)
        self.assertNotIn('ArgumentList.Add("--domain")', self.start)
        self.assertNotIn('ArgumentList.Add($ApiHostname)', self.start)
        self.assertIn('SetEnvironmentVariable("ALLOWED_ORIGINS", $FrontendOrigin, "Process")', self.start)
        self.assertIn("'\\.ngrok-free\\.(?:app|dev)$'", self.start)
        self.assertNotIn('"ALLOWED_ORIGINS", "*"', self.start)
        self.assertNotRegex(self.start + self.docs, r"(?i)trycloudflare")

    def test_start_verifies_local_agent_and_orders_readiness_checks(self):
        public_health_reasons = (
            "public-health-non-json-response",
            "public-health-network-timeout",
            "public-health-not-ready",
        )
        for reason in public_health_reasons:
            self.assertIn(f'"{reason}"', self.start)
        self.assertIn("{{.State.Health.Status}}", self.start)
        self.assertIn('"backend-health-timeout"', self.start)
        self.assertIn('$TunnelProcess.HasExited', self.start)
        self.assertIn('"ngrok-exited-early"', self.start)
        self.assertIn('http://127.0.0.1:4040/api/tunnels', self.start)
        self.assertIn('Invoke-RestMethod -Uri $AgentApiUri', self.start)
        self.assertIn('$_.public_url -ceq $ExpectedPublicUrl', self.start)
        self.assertIn('$Tunnel.config.addr -cne "http://127.0.0.1:8000"', self.start)
        self.assertNotIn('Write-Output $Agent', self.start)
        self.assertIn('Wait-ForCondition', self.start)
        self.assertIn('-TimeoutSec 2', self.start)
        self.assertIn('Start-Sleep -Milliseconds 500', self.start)
        self.assertLess(self.start.index('"backend-health-timeout"'), self.start.index('ArgumentList.Add("http")'))
        self.assertLess(self.start.index('ArgumentList.Add("http://127.0.0.1:8000")'), self.start.index('"expected-tunnel-not-registered"'))
        public_health_call = 'Wait-ForPublicHealth "$ExpectedPublicUrl/health" $TimeoutSeconds'
        self.assertIn(public_health_call, self.start)
        self.assertLess(self.start.index('"expected-tunnel-not-registered"'), self.start.index(public_health_call))
        self.assertIn('Stop-OwnedResources $TunnelProcess', self.start)

    def test_check_uses_required_inputs_agent_api_and_bounded_retries(self):
        for marker in ('FREE_NGROK_HTTPS_HOSTNAME', 'FREE_NGROK_FRONTEND_ORIGIN', 'http://127.0.0.1:4040/api/tunnels', 'Wait-ForCondition', 'Start-Sleep -Milliseconds 500'):
            self.assertIn(marker, self.check)
        self.assertNotIn('ArgumentList.Add("--domain")', self.check)

    def test_public_probes_use_the_ngrok_bypass_header_but_loopback_probes_do_not(self):
        header = '"ngrok-skip-browser-warning" = "1"'
        self.assertIn(header, self.start)
        self.assertIn('Invoke-WebRequest -Uri $Uri', self.start)
        self.assertIn(header, self.check)
        self.assertIn('if ($Base -ceq $ExpectedPublicUrl)', self.check)
        self.assertNotIn('Invoke-WebRequest -Uri "http://127.0.0.1:8000', self.start + self.check)
        self.assertIn('"public-health-non-json-response"', self.start)
        self.assertIn('"public-health-network-timeout"', self.start)
        self.assertIn('"public-health-non-json-response"', self.check)

    def test_hostname_contract_accepts_both_free_suffixes_and_rejects_unsafe_values(self):
        hostname = re.compile(
            r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
            r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*"
            r"\.ngrok-free\.(?:app|dev)$"
        )
        for value in ("demo-account.ngrok-free.app", "demo-account.ngrok-free.dev"):
            with self.subTest(accepted=value):
                self.assertIsNotNone(hostname.fullmatch(value))
        for value in (
            "https://demo-account.ngrok-free.dev", "demo-account.ngrok-free.dev/path",
            "demo-account.ngrok-free.dev:443", "demo-account.ngrok-free.dev?x=1",
            "demo-account.ngrok-free.dev#fragment", "*.ngrok-free.dev", "localhost",
            "demo-account.example.com", "demo_account.ngrok-free.app", "ngrok-free.dev",
        ):
            with self.subTest(rejected=value):
                self.assertIsNone(hostname.fullmatch(value))

    def test_frontend_origin_contract_is_exact_and_origin_only(self):
        origin = re.compile(r"^https://[^/]+\.netlify\.app$")
        self.assertIsNotNone(origin.fullmatch("https://bis-saarthi-ai-assistant.netlify.app"))
        for value in (
            "https://bis-saarthi-ai-assistant.netlify.app/",
            "https://bis-saarthi-ai-assistant.netlify.app/path",
            "https://bis-saarthi-ai-assistant.netlify.app?x=1",
            "https://bis-saarthi-ai-assistant.netlify.app#fragment",
            "https://bis-saarthi-ai-assistant.netlify.app:443",
        ):
            with self.subTest(rejected=value):
                self.assertIsNone(origin.fullmatch(value))

    def test_no_ngrok_credentials_are_handled_or_persisted(self):
        combined = self.start + self.check + self.stop
        self.assertNotRegex(combined, r"(?i)(ngrok.{0,30}(authtoken|api[_-]?key)|config add|--config)")
        self.assertNotIn("RedirectStandardOutput = $false", self.start)
        self.assertIn("BeginOutputReadLine()", self.start)
        self.assertIn("deploy/free-ngrok-demo/.runtime/", self.ignore)
        self.assertNotRegex(combined, r"(?i)(write-output|write-host).*\$(?:env:)?(?:.*key|.*token)")

    def test_generation_is_disabled_and_provider_secrets_are_empty_by_default(self):
        for marker in ('[switch]$EnableGeneration', '"LLM_PROVIDER", "disabled"', '"GROQ_API_KEY", ""', '"LLM_API_KEY", ""'):
            self.assertIn(marker, self.start)
        self.assertIn('"provider-secret-present"', self.check)

    def test_lifecycle_state_is_specific_to_its_own_ngrok_process(self):
        for content in (self.start, self.stop):
            self.assertIn('"ngrok-process.json"', content)
            self.assertIn("started_utc", content)
            self.assertIn("ProcessName", content)
            self.assertIn("ngrok", content)
            self.assertIn("StartTime.ToUniversalTime()", content)
        self.assertIn("Stop-Process -Id $TunnelProcess.Id", self.stop)
        self.assertIn("docker compose -f (Join-Path $Root \"compose.yaml\") -p $ProjectName down", self.stop)
        self.assertNotRegex(self.stop.lower(), r"docker (system|volume|image)|\\bprune\\b|taskkill|stop-process -name")

    def test_check_covers_public_health_cors_routes_ids_and_secrets(self):
        for marker in ("/health", "/api/v1/health", "/api/retrieve", "/api/v1/retrieve", "/api/chat", "/api/v1/chat", "Access-Control-Allow-Origin", "X-Request-ID", "printenv"):
            self.assertIn(marker, self.check)
        for code in ("missing-api-hostname", "missing-frontend-origin", "expected-tunnel-not-registered", "health-or-request-id-failed", "cors-origin-mismatch", "route-validation-failed", "provider-secret-present"):
            self.assertIn(f'"{code}"', self.check)

    def test_docs_cover_operations_limits_and_production_boundary(self):
        for phrase in ("Create a free ngrok account", "local configuration", "assigned free development domain", "VITE_API_BASE_URL", "Start and validate", "Shut down", "revoke it", "powered", "demo-only", "production scaling design", "Cloudflare named-tunnel"):
            self.assertIn(phrase, self.docs)
        self.assertNotRegex(self.docs, r"(?i)(?:C:|/home/|/Users/|authtoken\s*=)")


if __name__ == "__main__":
    unittest.main()
