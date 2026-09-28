import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ingestion import extract_fmcs_ocr as ocr
from ingestion.fmcs_ocr_chunks import group_lines, stable_chunk_id, meaningful


class FmcsOcrTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.raw = self.root / "raw"
        self.path = self.raw / "fmcs/ApplicationFormV.pdf"
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"approved")
        self.hash = hashlib.sha256(b"approved").hexdigest()
        self.approved = {"fmcs_application_form_v": {**ocr.TARGETS["fmcs_application_form_v"], "incoming_sha256": self.hash, "canonical_official_url": "https://example.test/form.pdf"}}

    def tearDown(self): self.temp.cleanup()

    def test_hash_mismatch_rejected(self):
        self.approved["fmcs_application_form_v"]["incoming_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            ocr.verified_source("fmcs_application_form_v", self.raw, self.approved)

    def test_unapproved_source_rejected(self):
        with self.assertRaisesRegex(ValueError, "unapproved source ID"):
            ocr.verified_source("not_approved", self.raw, self.approved)

    def test_embedded_text_skips_ocr(self):
        self.approved["fmcs_application_form_v"]["ocr_required"] = False
        with patch.object(ocr, "embedded_text_pages", return_value=["A" * 200]), patch.object(ocr, "ocr_page") as page:
            result = ocr.extract_source("fmcs_application_form_v", self.raw, self.approved, self.root / "out")
        self.assertFalse(result["ocr_used"]); page.assert_not_called()

    def test_scanned_pdf_uses_ocr_and_preserves_pages(self):
        image = self.root / "image.png"; image.write_bytes(b"rendered")
        def fake_page(_pdf, page, _workdir, _run):
            return image, f"FMCS APPLICATION FORM\nField label {page}\n____\n☐\n", "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t1\t0\t0\t0\t0\t95\tFMCS\n"
        with patch.object(ocr, "embedded_text_pages", return_value=["", ""]), patch.object(ocr, "tool_versions", return_value={"tesseract":"x", "pdftoppm":"y"}), patch.object(ocr, "ocr_page", side_effect=fake_page):
            result = ocr.extract_source("fmcs_application_form_v", self.raw, self.approved, self.root / "out")
        self.assertTrue(result["ocr_used"]); self.assertEqual([x["page_number"] for x in result["sidecars"]], [1, 2])
        self.assertTrue((self.root / "out/sidecars/fmcs_application_form_v/page-0001.json").is_file())

    def test_deterministic_sidecar_and_stable_chunk_ids(self):
        image = self.root / "image.png"; image.write_bytes(b"rendered")
        def fake_page(_pdf, _page, _workdir, _run): return image, "APPLICATION FORM\nApplicant name\n____\n", "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t1\t0\t0\t0\t0\t96\tAPPLICATION\n"
        kwargs = dict(run=ocr.command)
        with patch.object(ocr, "embedded_text_pages", return_value=[""]), patch.object(ocr, "tool_versions", return_value={"tesseract":"x", "pdftoppm":"y"}), patch.object(ocr, "ocr_page", side_effect=fake_page):
            first = ocr.extract_source("fmcs_application_form_v", self.raw, self.approved, self.root / "one", **kwargs)
            second = ocr.extract_source("fmcs_application_form_v", self.raw, self.approved, self.root / "two", **kwargs)
        self.assertEqual(first["sidecars"], second["sidecars"])
        self.assertEqual([x["id"] for x in first["chunks"]], [x["id"] for x in second["chunks"]])

    def test_blank_noisy_fields_rejected_and_headings_retained(self):
        accepted, rejected = ocr.filter_lines("FMCS APPLICATION CHECKLIST\n____\n☐\n12\n@@@\nApplicant details\nName", [])
        self.assertIn("FMCS APPLICATION CHECKLIST", accepted); self.assertIn("Applicant details", accepted); self.assertIn("Name", accepted)
        self.assertEqual({row["reason"] for row in rejected}, {"blank_field", "isolated_checkbox", "standalone_serial_number", "symbol_dominated_noise"})

    def test_repeated_page_furniture_rejected(self):
        accepted, rejected = ocr.remove_repeated_page_furniture(["BIS HEADER", "Checklist item"], [], {"bis header"})
        self.assertEqual(accepted, ["Checklist item"])
        self.assertEqual(rejected, [{"text": "BIS HEADER", "reason": "repeated_page_furniture"}])

    def test_fmcs_metadata_and_no_network_provider(self):
        sidecar = {"page_number": 1, "filename": "x.pdf", "source_sha256": "a", "official_url": "u", "tsv_confidence_summary": {"mean_confidence": 90}, "accepted_lines": ["FMCS heading", "Printed application instruction for the applicant to complete."]}
        row = ocr.chunk_rows("fmcs_application_form_v", self.approved["fmcs_application_form_v"], sidecar, Path("sidecars/x.json"))[0]
        self.assertEqual(row["metadata"]["category"], "fmcs"); self.assertEqual(row["metadata"]["scope"], "fmcs_only")
        self.assertEqual(row["metadata"]["extraction_method"], "ocr"); self.assertIn("domestic", row["metadata"]["restriction"])
        with patch("subprocess.run") as run:
            ocr.sha256_file(self.path)
        run.assert_not_called()

    def test_page_local_grouping_meaningful_content_and_stable_ids(self):
        lines = ["CHECKLIST HEADING", "1. Applicant details are complete and attached to the application.", "2. Test facilities are available at the factory premises."]
        groups = group_lines(lines)
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(meaningful("\n".join(group)) for group in groups))
        self.assertEqual(stable_chunk_id("fmcs_application_checklist", 1, groups[0]), stable_chunk_id("fmcs_application_checklist", 1, groups[0]))
        self.assertNotEqual(stable_chunk_id("fmcs_application_checklist", 1, groups[0]), stable_chunk_id("fmcs_application_checklist", 2, groups[0]))


if __name__ == "__main__": unittest.main()
