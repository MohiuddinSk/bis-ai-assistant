"""Real-source contract for the two approved offline OCR inputs.

Run this only in the ingestion-ocr container, where Poppler and Tesseract are
available and the two FMCS source mounts are read-only.
"""
import tempfile
import unittest
import shutil
from pathlib import Path

from ingestion import extract_fmcs_ocr as ocr


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    shutil.which("pdftoppm") and shutil.which("tesseract"),
    "requires the verified ingestion-ocr image with Poppler and Tesseract",
)
class RealFmcsOcrIntegrationTests(unittest.TestCase):
    def test_approved_sources_produce_ocr_sidecars_and_fmcs_chunks(self):
        approved = ocr.load_approved_sources(ROOT / "docs/corpus_v4_source_manifest.json")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            results = [ocr.extract_source(source_id, ROOT / "data/raw", approved, output) for source_id in sorted(ocr.TARGETS)]
            self.assertEqual([item["source_id"] for item in results], sorted(ocr.TARGETS))
            self.assertTrue(all(item["ocr_used"] for item in results))
            for item in results:
                self.assertGreater(item["page_count"], 0)
                self.assertTrue(item["chunks"])
                self.assertTrue(all(row["metadata"]["scope"] == "fmcs_only" for row in item["chunks"]))
                self.assertTrue(all(row["metadata"]["extraction_method"] == "ocr" for row in item["chunks"]))
                self.assertTrue(all(page["extraction_method"] == "ocr" for page in item["sidecars"]))
                self.assertEqual(len({row["id"] for row in item["chunks"]}), len(item["chunks"]))


if __name__ == "__main__": unittest.main()
