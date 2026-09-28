"""Deterministic safety tests for the pre-ingestion official-source gate."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from corpus_source_verification import build_manifest, is_allowed_official_url, validate_manifest  # noqa: E402


class CorpusSourceVerificationTests(unittest.TestCase):
    def _review(self) -> dict:
        return {"files": [
            {"classification": "new candidate", "original_relative_path": "categories/Application Checklist/ApplicationFormV.pdf", "sha256": "3d15850b2863091ffe20a18183ca33332ded340c30fe3b6b57c3cf5a499c69a7"},
            {"classification": "new candidate", "original_relative_path": "unknown.pdf", "sha256": "abc"},
            {"classification": "exact duplicate", "original_relative_path": "already.pdf", "sha256": "def"},
        ]}

    def test_allowed_authority_hosts_are_https_and_exact(self) -> None:
        self.assertTrue(is_allowed_official_url("https://www.bis.gov.in/path"))
        self.assertTrue(is_allowed_official_url("https://lims.bis.gov.in/home/labs/"))
        self.assertFalse(is_allowed_official_url("http://www.bis.gov.in/path"))
        self.assertFalse(is_allowed_official_url("https://bis.gov.in.evil.example/path"))
        self.assertFalse(is_allowed_official_url("https://example.com/bis"))

    def test_manifest_excludes_duplicates_and_preserves_fmcs_scope_warning(self) -> None:
        manifest = build_manifest(self._review())
        self.assertEqual(len(manifest["records"]), 2)
        form = manifest["records"][0]
        self.assertEqual(form["match"], "exact")
        self.assertEqual(form["decision"], "active")
        self.assertEqual(form["scheme_product_scope"], "FMCS")
        self.assertIn("FMCS", form["required_runtime_warning"])

    def test_filename_only_authority_cannot_activate_a_source(self) -> None:
        unknown = build_manifest(self._review())["records"][1]
        self.assertEqual(unknown["decision"], "secondary")
        self.assertIsNone(unknown["canonical_official_url"])

    def test_manifest_rejects_unverified_active_or_missing_freshness_warning(self) -> None:
        with self.assertRaises(ValueError):
            validate_manifest([{ "incoming_path": "x", "incoming_sha256": "a", "canonical_official_url": "https://www.bis.gov.in/x", "downloaded_canonical_sha256": None, "match": "no match", "decision": "active", "required_runtime_warning": "x", "scheme_product_scope": "Unresolved" }])
        with self.assertRaises(ValueError):
            validate_manifest([{ "incoming_path": "x", "incoming_sha256": "a", "canonical_official_url": "https://lims.bis.gov.in/x", "downloaded_canonical_sha256": None, "match": "no match", "decision": "active with freshness warning", "required_runtime_warning": "", "scheme_product_scope": "Unresolved" }])


if __name__ == "__main__":
    unittest.main()
