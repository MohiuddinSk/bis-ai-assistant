"""Static guardrails for the named-tunnel SIH demo workflow."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SecureDemoDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.docs = (ROOT / "docs" / "SECURE_DEMO_DEPLOYMENT.md").read_text(encoding="utf-8")
        self.start = (ROOT / "deploy" / "start-secure-sih-demo.ps1").read_text(encoding="utf-8")
        self.check = (ROOT / "deploy" / "check-secure-sih-demo.ps1").read_text(encoding="utf-8")
        self.stop = (ROOT / "deploy" / "stop-secure-sih-demo.ps1").read_text(encoding="utf-8")

    def test_required_artifacts_and_local_only_compose_port(self):
        for path in (
            "deploy/start-secure-sih-demo.ps1",
            "deploy/check-secure-sih-demo.ps1",
            "deploy/stop-secure-sih-demo.ps1",
            "docs/SECURE_DEMO_DEPLOYMENT.md",
        ):
            self.assertTrue((ROOT / path).is_file(), path)
        self.assertIn('"127.0.0.1:${BACKEND_HOST_PORT:-8000}:8000"', self.compose)
        self.assertNotIn('"8000:8000"', self.compose)

    def test_named_tunnel_is_required_and_quick_tunnels_are_prohibited(self):
        for content in (self.start, self.docs):
            self.assertIn("SIH_TUNNEL_NAME", content)
            self.assertIn("cloudflared", content.lower())
        self.assertIn('ArgumentList.Add("tunnel")', self.start)
        self.assertIn('ArgumentList.Add("run")', self.start)
        combined = self.start + self.check + self.stop
        self.assertNotRegex(combined, r"(?i)trycloudflare|--url\b|quick\s*tunnel")

    def test_explicit_hostname_and_narrow_cors_contract(self):
        for name in ("SIH_FRONTEND_HOSTNAME", "SIH_API_HOSTNAME"):
            self.assertIn(name, self.start)
            self.assertIn(name, self.check)
            self.assertIn(name, self.docs)
        self.assertIn('[Environment]::SetEnvironmentVariable("ALLOWED_ORIGINS", "https://$FrontendHostname", "Process")', self.start)
        self.assertIn("$FrontendHostname -eq $ApiHostname", self.start)
        self.assertNotIn("ALLOWED_ORIGINS=*", self.start)

    def test_generation_is_disabled_by_default_and_opt_in_requires_secrets(self):
        self.assertIn("[switch]$EnableGeneration", self.start)
        self.assertIn('[Environment]::SetEnvironmentVariable("LLM_PROVIDER", "disabled", "Process")', self.start)
        self.assertIn('[Environment]::SetEnvironmentVariable("GROQ_API_KEY", "", "Process")', self.start)
        self.assertIn('[Environment]::SetEnvironmentVariable("LLM_API_KEY", "", "Process")', self.start)
        self.assertIn("-EnableGeneration with groq requires GROQ_API_KEY", self.start)
        self.assertIn("-EnableGeneration with openai_compatible requires LLM_API_KEY", self.start)

    def test_scripts_do_not_accept_or_log_cloudflare_tokens(self):
        combined = self.start + self.check + self.stop
        self.assertNotRegex(combined, r"(?i)(--token|cloudflare.{0,20}token|cloudflare.{0,20}api[_-]?key|cert\.pem)")
        self.assertNotRegex(combined, r"(?i)(write-output|write-host).*\$(?:env:)?(?:.*key|.*token|.*config)")
        self.assertIn("SIH_CLOUDFLARED_CONFIG", self.start)
        self.assertIn(".cloudflared/", self.ignore)
        self.assertIn("deploy/.secure-sih-demo-runtime/", self.ignore)

    def test_lifecycle_is_scoped_to_demo_resources(self):
        for script in (self.start, self.check, self.stop):
            self.assertIn('$ProjectName = "sih-secure-demo"', script)
        self.assertIn('docker compose -f (Join-Path $Root "compose.yaml") -p $ProjectName up --build --detach backend', self.start)
        self.assertIn('docker compose -f (Join-Path $Root "compose.yaml") -p $ProjectName down', self.stop)
        self.assertIn("$TunnelProcess.ProcessName -match '^cloudflared", self.stop)
        self.assertIn("Stop-Process -Id $TunnelProcess.Id", self.stop)
        self.assertNotRegex(self.stop.lower(), r"docker (system|volume|image)|\bprune\b|docker rm")

    def test_documentation_covers_operator_requirements(self):
        for heading in (
            "Authenticate Cloudflare", "Create the named tunnel", "Route DNS hostname",
            "Start the backend and tunnel", "Configure Netlify", "Configure ALLOWED_ORIGINS",
            "Configure Cloudflare rate limiting", "Validate", "Shut down",
            "Revoke credentials and roll back", "Production boundary",
        ):
            self.assertIn(heading, self.docs)
        self.assertIn("demo-only", self.docs.lower())
        self.assertIn("VITE_API_BASE_URL", self.docs)
        self.assertIn("Quick Tunnel", self.docs)
        self.assertNotRegex(self.docs, r"https://[^\s`]*trycloudflare\.com")

    def test_no_machine_specific_path_or_committed_secret_placeholder(self):
        combined = self.start + self.check + self.stop + self.docs
        self.assertNotRegex(combined, r"(?i)(C:\\\\Users\\|/home/|/Users/|credentials-file:\s*[A-Za-z]:)")
        self.assertNotRegex(combined, r"(?i)(secret\s*=\s*['\"]?[A-Za-z0-9]{12,}|token\s*=\s*['\"]?[A-Za-z0-9]{12,})")


if __name__ == "__main__":
    unittest.main()
