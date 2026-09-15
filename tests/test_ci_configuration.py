import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/quality-gates.yml"
DEPENDABOT_PATH = ROOT / ".github/dependabot.yml"
BACKEND_TESTS = [
    "tests.test_api", "tests.test_chat_api", "tests.test_chat_understanding_api",
    "tests.test_compliance_api", "tests.test_container_configuration", "tests.test_cors_settings",
    "tests.test_data_contract", "tests.test_documents", "tests.test_generation_factory",
    "tests.test_guided_fact_plan", "tests.test_openai_compatible_generator",
    "tests.test_personalized_assistant", "tests.test_provider_disabled_api",
    "tests.test_question_understanding", "tests.test_retrieval_disabled_api",
    "tests.test_retrieval_factory", "tests.test_retrieval_provider_contract",
    "tests.test_standard_explanation.StandardExplanationApiTests",
    "tests.test_standard_explanation.StandardExplanationUnderstandingGuardTests",
    "tests.test_ci_artifacts", "tests.test_ci_configuration",
]


class CiConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.workflow = yaml.safe_load(cls.raw)
        cls.jobs = cls.workflow["jobs"]

    def test_exact_triggers_are_safe_and_unfiltered(self):
        self.assertEqual(set(self.workflow["on"]), {"pull_request", "push", "workflow_dispatch"})
        self.assertEqual(self.workflow["on"]["pull_request"], {"branches": ["main"]})
        self.assertEqual(self.workflow["on"]["push"], {"branches": ["main"]})
        self.assertNotIn("pull_request_target", self.workflow["on"])
        for trigger in ("pull_request", "push"):
            self.assertNotIn("paths", self.workflow["on"][trigger])
            self.assertNotIn("paths-ignore", self.workflow["on"][trigger])
        self.assertEqual(self.workflow["concurrency"], {
            "group": "${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}",
            "cancel-in-progress": True,
        })

    def test_permissions_and_jobs_are_minimal(self):
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        self.assertEqual(set(self.jobs), {"backend-unit", "frontend", "data-and-configuration"})
        self.assertEqual([self.jobs[key]["name"] for key in self.jobs],
                         ["Backend unit", "Frontend", "Data and configuration"])
        for job in self.jobs.values():
            self.assertEqual(job["runs-on"], "ubuntu-latest")
            self.assertNotIn("permissions", job)
        self.assertEqual(self.jobs["backend-unit"]["timeout-minutes"], 15)
        self.assertEqual(self.jobs["frontend"]["timeout-minutes"], 10)
        self.assertEqual(self.jobs["data-and-configuration"]["timeout-minutes"], 10)

    def test_actions_are_immutable_and_checkout_is_shallow(self):
        expected = {
            "actions/checkout": "11bd71901bbe5b1630ceea73d27597364c9af683",
            "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
            "actions/setup-node": "49933ea5288caeca8642d1e84afbd3f7d6820020",
        }
        for job in self.jobs.values():
            for step in job["steps"]:
                if "uses" not in step:
                    continue
                action, sha = step["uses"].split("@", 1)
                self.assertIn(action, expected)
                self.assertEqual(sha, expected[action])
                self.assertRegex(sha, r"^[0-9a-f]{40}$")
                if action == "actions/checkout":
                    self.assertEqual(step["with"], {"persist-credentials": False, "fetch-depth": 1})

    def test_backend_environment_and_exact_test_selection(self):
        backend = self.jobs["backend-unit"]
        self.assertEqual(backend["env"], {
            "RETRIEVAL_PROVIDER": "disabled", "LLM_PROVIDER": "disabled", "GROQ_API_KEY": "",
            "GROQ_MODEL": "", "LLM_API_KEY": "", "LLM_BASE_URL": "", "LLM_MODEL": "",
            "LLM_ALLOWED_HOSTS": "", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false", "PYTHONUTF8": "1",
        })
        command = backend["steps"][-1]["run"]
        selected = re.findall(r"tests(?:\.\w+)+", command)
        self.assertEqual(selected, BACKEND_TESTS)
        for excluded in ("real_data", "retrieval.test_retrieval", "StandardExplanationRealIndexTests"):
            self.assertNotIn(excluded, command)
        python_setup = backend["steps"][1]["with"]
        self.assertEqual(python_setup["cache"], "pip")
        self.assertEqual(python_setup["cache-dependency-path"], "requirements-ci-light.txt")

    def test_frontend_commands_and_cache_are_exact(self):
        frontend = self.jobs["frontend"]
        self.assertEqual(frontend["defaults"]["run"]["working-directory"], "frontend")
        self.assertEqual(frontend["steps"][1]["with"], {
            "node-version": "22.19.0", "cache": "npm", "cache-dependency-path": "frontend/package-lock.json",
        })
        self.assertEqual(frontend["steps"][-1]["run"].splitlines(), [
            "npm ci", "npm run lint", "npm run test -- --run", "npm run build",
        ])

    def test_data_job_is_read_only_and_commands_are_safe(self):
        command = self.jobs["data-and-configuration"]["steps"][-1]["run"]
        self.assertIn("python scripts/check_ci_artifacts.py", command)
        self.assertIn("git diff --check", command)
        self.assertIn("git diff --exit-code", command)
        for forbidden in ("docker", "ingestion/", "retrieval/test_retrieval.py", "deploy", "upload-artifact"):
            self.assertNotIn(forbidden, command.lower())

    def test_no_secrets_or_unsafe_cache_targets(self):
        self.assertNotIn("secrets.", self.raw)
        self.assertNotIn("github.event.pull_request.title", self.raw)
        self.assertNotIn("github.event.head_commit.message", self.raw)
        self.assertNotRegex(self.raw, r"(?im)^\s*permissions:\s*(write|\{.*write)")
        self.assertNotIn("HF_HOME", self.raw)
        self.assertNotIn("HUGGINGFACE_HUB_CACHE", self.raw)
        self.assertNotIn("TRANSFORMERS_CACHE", self.raw)
        self.assertNotIn("data/chroma", self.raw)
        for job in self.jobs.values():
            for step in job["steps"]:
                configured = step.get("with", {})
                if configured.get("cache") == "pip":
                    self.assertEqual(configured.get("cache-dependency-path"), "requirements-ci-light.txt")
                if configured.get("cache") == "npm":
                    self.assertEqual(configured.get("cache-dependency-path"), "frontend/package-lock.json")

    def test_dependabot_configuration_is_limited_and_independently_reviewable(self):
        self.assertTrue(DEPENDABOT_PATH.is_file())
        dependabot = yaml.safe_load(DEPENDABOT_PATH.read_text(encoding="utf-8"))
        self.assertIsInstance(dependabot, dict)
        self.assertEqual(dependabot.get("version"), 2)
        updates = dependabot.get("updates")
        self.assertIsInstance(updates, list)
        expected_limits = {
            ("pip", "/"): 5,
            ("npm", "/frontend"): 5,
            ("github-actions", "/"): 3,
        }
        self.assertEqual(
            {(entry.get("package-ecosystem"), entry.get("directory")) for entry in updates if isinstance(entry, dict)},
            set(expected_limits),
        )
        self.assertEqual(len(updates), len(expected_limits))
        expected_schedule = {
            "interval": "weekly", "day": "monday", "time": "04:00", "timezone": "Asia/Kolkata",
        }
        forbidden = {
            "registries", "credentials", "secrets", "reviewers", "assignees", "labels", "groups", "allow",
            "auto-merge", "automerge", "insecure-external-code-execution",
        }
        major_only_ignore = [{
            "dependency-name": "*",
            "update-types": ["version-update:semver-major"],
        }]
        for entry in updates:
            self.assertIsInstance(entry, dict)
            key = (entry["package-ecosystem"], entry["directory"])
            self.assertIn(key, expected_limits)
            self.assertEqual(entry.get("target-branch"), "main")
            self.assertEqual(entry.get("schedule"), expected_schedule)
            self.assertEqual(entry.get("open-pull-requests-limit"), expected_limits[key])
            self.assertEqual(entry.get("commit-message"), {"prefix": "deps"})
            self.assertEqual(entry.get("ignore"), major_only_ignore)
            self.assertTrue(forbidden.isdisjoint(entry))
            self.assertNotIn("rebase-strategy", entry)
            self.assertNotIn("pull-request-branch-name", entry)
        self.assertTrue(forbidden.isdisjoint(dependabot))


if __name__ == "__main__":
    unittest.main()
