"""Focused non-destructive tests for the incoming-corpus Phase 1.5 review."""
from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from corpus_review import (  # noqa: E402
    _eligibility,
    inspect_docx,
    near_duplicate_similarity,
    normalize_text,
    normalized_text_hash,
    review,
)


class CorpusReviewTests(unittest.TestCase):
    def _valid_docx(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("word/document.xml", "<w:document xmlns:w='x'/>")

    def test_normalized_hash_and_near_duplicate_are_whitespace_and_case_stable(self) -> None:
        left = "BIS  IS 15644\nProduct Manual"
        right = "bis is-15644 product manual"
        self.assertEqual(normalized_text_hash(left), normalized_text_hash(right))
        self.assertGreaterEqual(near_duplicate_similarity(left, right), 0.95)

    def test_valid_docx_is_not_reported_as_corrupt_when_python_docx_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "structured.docx"
            self._valid_docx(path)
            _, _, error = inspect_docx(path)
        self.assertFalse((error or "").startswith("corrupt_document"))

    def test_malformed_docx_fails_safely(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "broken.docx"
            path.write_bytes(b"not an Office document")
            _, _, error = inspect_docx(path)
        self.assertEqual(error, "corrupt_document:not_zip")

    def test_eligibility_rules_keep_historical_and_secondary_out_of_active_retrieval(self) -> None:
        self.assertEqual(_eligibility("historical/superseded", "issuer", None, "old.pdf")[0], "historical retrieval only (disabled by default)")
        self.assertEqual(_eligibility("structured/team-created secondary source", "issuer", None, "source.docx")[0], "secondary retrieval only (pending provenance)")
        self.assertEqual(_eligibility("new candidate", "No issuing authority established by bounded extracted text", None, "new.pdf")[0], "quarantine pending provenance")

    def test_review_is_non_destructive_and_detects_incoming_exact_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incoming = root / "incoming"
            raw = root / "raw"
            incoming.mkdir(); raw.mkdir()
            first = incoming / "a.docx"; second = incoming / "nested" / "b.docx"
            second.parent.mkdir()
            self._valid_docx(first)
            second.write_bytes(first.read_bytes())
            (raw / "canonical.docx").write_bytes(first.read_bytes())
            before = {path.relative_to(root): path.read_bytes() for path in incoming.rglob("*") if path.is_file()}
            report = review(incoming, raw)
            after = {path.relative_to(root): path.read_bytes() for path in incoming.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(report["total_files"], 2)
        self.assertTrue(all(row["classification"] == "exact duplicate" for row in report["files"]))


if __name__ == "__main__":
    unittest.main()
