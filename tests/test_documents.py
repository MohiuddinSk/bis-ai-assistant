import json
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.documents import SourceDocumentRegistry


class SourceDocumentRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.raw = root / "raw"
        self.raw.mkdir()
        (self.raw / "trusted.pdf").write_bytes(b"%PDF-1.4\n")
        self.registry = root / "registry.json"
        self.registry.write_text(json.dumps([{"source_filename": "trusted.pdf"}]), encoding="utf-8")
        self.sources = SourceDocumentRegistry(self.raw, self.registry)

    def tearDown(self):
        self.temp.cleanup()

    def test_registered_pdf_resolves(self):
        self.assertEqual(self.sources.resolve("trusted.pdf"), (self.raw / "trusted.pdf").resolve())

    def test_rejects_unknown_non_pdf_and_path_attacks_without_path_leakage(self):
        for value in ("unknown.pdf", "trusted.txt", "../trusted.pdf", "%2e%2e%2ftrusted.pdf", "..\\trusted.pdf", "C:\\trusted.pdf"):
            with self.subTest(value=value), self.assertRaises(HTTPException) as raised:
                self.sources.resolve(value)
            self.assertEqual(raised.exception.status_code, 404)
            self.assertNotIn(str(self.raw), str(raised.exception.detail))

    def test_registered_missing_file_fails_safely(self):
        (self.raw / "trusted.pdf").unlink()
        with self.assertRaises(HTTPException) as raised:
            self.sources.resolve("trusted.pdf")
        self.assertEqual(raised.exception.status_code, 404)
