"""Contracts for the read-only answer-coverage diagnostic."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.retrieval_provider import RetrievalHit
from scripts import audit_answer_coverage as audit


class _FakeRetriever:
    def count(self):
        return 1

    def indexed_chunks(self):
        return (RetrievalHit("chunk-1", "IS 15644 applies to electric toys.", {
            "source_filename": "official.pdf", "page_start": 1, "page_end": 1,
        }, 0.0),)

    def search(self, question, k=5):
        return self.indexed_chunks()


class _FakeService:
    provider_seen = False

    def __init__(self, **kwargs):
        self.generator = kwargs["generator"]
        _FakeService.provider_seen = self.generator is not None

    def _retrieve_evidence(self, request, routing, understanding):
        return [SimpleNamespace(chunk_id="chunk-1", text="IS 15644 applies to electric toys.",
                                source_filename="official.pdf", page_start=1, page_end=1,
                                distance=0.0)]

    def _build_evidence_plan(self, question, evidence, routing, understanding):
        return SimpleNamespace(category="test", roles={"primary": (evidence[0], evidence[0].text)})

    def _coverage_queries(self, question, routing, understanding):
        return ["controlled coverage query"]

    def chat(self, request, understanding=None):
        return SimpleNamespace(
            answer="IS 15644 applies to electric toys. Verify applicability.",
            answer_sections=[], citations=[],
        )


class AnswerCoverageAuditTests(unittest.TestCase):
    @property
    def _script(self):
        return audit.ROOT / "scripts" / "audit_answer_coverage.py"

    def _cli(self, *args, cwd):
        return subprocess.run(
            [sys.executable, str(self._script), *args], cwd=cwd, text=True,
            capture_output=True, check=False, timeout=30,
        )

    def test_cli_help_bootstraps_project_imports_from_repository_root(self):
        before = audit._snapshot()
        result = self._cli("--help", cwd=audit.ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Read-only coverage audit", result.stdout)
        self.assertNotIn(str(audit.ROOT), result.stdout + result.stderr)
        self.assertEqual(before, audit._snapshot())

    def test_cli_help_bootstraps_project_imports_from_another_directory(self):
        before = audit._snapshot()
        with tempfile.TemporaryDirectory() as directory:
            result = self._cli("--help", cwd=directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--output", result.stdout)
        self.assertNotIn(str(audit.ROOT), result.stdout + result.stderr)
        # ``--help`` exits before run_audit, so no retriever/provider is built.
        self.assertNotIn("collection=", result.stdout)
        self.assertEqual(before, audit._snapshot())

    def test_cli_rejects_protected_output_without_mutating_protected_paths(self):
        before = audit._snapshot()
        result = self._cli("--output", "data/raw/audit.json", cwd=audit.ROOT)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Audit output must be outside protected paths", result.stderr)
        self.assertNotIn(str(audit.ROOT), result.stdout + result.stderr)
        self.assertEqual(before, audit._snapshot())

    def test_contract_contains_all_twelve_questions_and_valid_codes(self):
        self.assertEqual([item.identifier for item in audit.AUDIT_QUESTIONS], [f"Q{number:02d}" for number in range(1, 13)])
        self.assertEqual(len(audit.QUALITY_RATINGS), 5)
        self.assertEqual(len(audit.CAUSE_CODES), 9)
        self.assertIn("SUPPORTED", audit.CAUSE_CODES)
        self.assertEqual(set(audit.CAUSE_CODE_DESCRIPTIONS), set(audit.CAUSE_CODES))

    def test_output_destination_rejects_protected_paths(self):
        for protected in audit.PROTECTED_PATHS:
            with self.subTest(protected=protected):
                with self.assertRaises(ValueError):
                    audit._output_path(f"{protected}/audit.json")

    def test_audit_is_deterministic_read_only_and_never_constructs_provider(self):
        before = {"data/raw/example.pdf": "same"}
        with (
            patch.object(audit, "LocalChromaRetriever", _FakeRetriever),
            patch.object(audit, "ChatService", _FakeService),
            patch.object(audit, "_processed_texts", return_value=[]),
            patch.object(audit, "_raw_pdf_texts", return_value=([], True)),
            patch.object(audit, "index_integrity", return_value={
                "collection_count": 1, "unique_ids": 1, "unique_normalized_text_hashes": 1,
                "duplicate_normalized_text_records": 0,
                "unique_source_page_chunk_identities": 1,
                "duplicate_source_page_chunk_identity_records": 0,
            }),
            patch.object(audit, "_snapshot", side_effect=[before, before, before, before]),
        ):
            first = audit.run_audit()
            second = audit.run_audit()
        self.assertFalse(_FakeService.provider_seen)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(len(first["questions"]), 12)
        self.assertTrue(all(row["quality"] in audit.QUALITY_RATINGS for row in first["questions"]))
        self.assertTrue(all(row["primary_cause"] in audit.CAUSE_CODES for row in first["questions"]))
        self.assertTrue(all("pending" not in str(row).lower() for row in first["questions"]))
        serialized = json.dumps(first, sort_keys=True)
        self.assertNotIn(str(audit.ROOT), serialized)
        self.assertNotRegex(serialized.lower(), r"(?:api[_-]?key|authorization|secret)")
        for row in first["questions"]:
            self.assertTrue(row["citation_integrity"])
            self.assertTrue(all(item["cause"] in audit.CAUSE_CODES for item in row["missing_facts"]))

    def test_index_metrics_are_deterministic_and_internally_consistent(self):
        first = RetrievalHit("one", "same  text", {
            "source_filename": "one.pdf", "page_start": 1, "page_end": 1, "chunk_type": "document_text",
        }, 0.0)
        second = RetrievalHit("two", "same text", {
            "source_filename": "two.pdf", "page_start": 1, "page_end": 1, "chunk_type": "document_text",
        }, 0.0)
        metrics = audit.index_metrics([first, second])
        self.assertEqual(metrics["collection_count"], 2)
        self.assertEqual(metrics["unique_ids"], 2)
        self.assertEqual(metrics["unique_normalized_text_hashes"], 1)
        self.assertEqual(metrics["duplicate_normalized_text_records"], 1)
        self.assertLessEqual(metrics["unique_ids"], metrics["collection_count"])
        self.assertLessEqual(metrics["unique_normalized_text_hashes"], metrics["collection_count"])
        self.assertEqual(metrics, audit.index_metrics([first, second]))

    def test_report_fields_are_safe_and_do_not_leak_paths_or_secret_words(self):
        excerpt = audit.safe_excerpt("  short\n excerpt  ")
        self.assertEqual(excerpt, "short excerpt")
        self.assertNotIn(str(Path.cwd()), excerpt)

    def test_finalized_fact_requires_a_valid_citation(self):
        check = audit.FactCheck("condition", ("electric function",), False)
        sections = [{"content": "A toy has an electric function.", "items": [], "citation_ids": ["S1"]}]
        self.assertTrue(audit._matches_finalized_section(sections, [{"citation_id": "S1"}], check))
        self.assertFalse(audit._matches_finalized_section(sections, [], check))

    def test_ranked_candidate_diagnostic_omits_boundary_varying_membership(self):
        first = RetrievalHit("near-tie-a", "first", {}, 0.144343)
        second = RetrievalHit("near-tie-b", "second", {}, 0.144369)
        self.assertEqual(
            audit._ranked_candidate_diagnostic([first, second]),
            audit._ranked_candidate_diagnostic([second]),
        )

    def test_two_fresh_cli_audits_are_identical_and_q11_has_no_missing_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            first_run = self._cli("--output", str(first), cwd=audit.ROOT)
            second_run = self._cli("--output", str(second), cwd=audit.ROOT)
            self.assertEqual(first_run.returncode, 0, first_run.stderr)
            self.assertEqual(second_run.returncode, 0, second_run.stderr)
            first_bytes, second_bytes = first.read_bytes(), second.read_bytes()
        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(hashlib.sha256(first_bytes).hexdigest(), hashlib.sha256(second_bytes).hexdigest())
        report = json.loads(first_bytes)
        q11 = next(row for row in report["questions"] if row["id"] == "Q11")
        self.assertEqual(q11["quality"], "GOOD")
        self.assertEqual(q11["primary_cause"], "CORRECT_LIMITATION")
        self.assertEqual(q11["missing_facts"], [])
        self.assertTrue(all(
            entry["cause"] != "SUPPORTED"
            for row in report["questions"] for entry in row["missing_facts"]
        ))


if __name__ == "__main__":
    unittest.main()
