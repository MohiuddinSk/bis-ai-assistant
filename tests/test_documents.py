import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.documents import SourceDocumentRegistry
from backend.main import create_app


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


class SourceDocumentRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.raw = root / "raw"
        self.raw.mkdir()
        self.pdf = self.raw / "trusted.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\n")
        registry_path = root / "registry.json"
        registry_path.write_text(json.dumps([{"source_filename": "trusted.pdf"}]), encoding="utf-8")
        registry = SourceDocumentRegistry(self.raw, registry_path)
        with patch("backend.main.SourceDocumentRegistry", return_value=registry):
            self.app = create_app(
                retriever_factory=lambda: SimpleNamespace(collection=SimpleNamespace(count=lambda: 1)),
                generator_factory=lambda: SimpleNamespace(model="fake"),
            )

    def tearDown(self):
        self.temp.cleanup()

    def test_legacy_and_v1_document_routes_preserve_registry_security(self):
        with TestClient(self.app) as client:
            for prefix in ("/api/documents", "/api/v1/documents"):
                success = client.get(f"{prefix}/trusted.pdf")
                self.assertEqual(success.status_code, 200)
                self.assertEqual(success.content, b"%PDF-1.4\n")
                self.assertIn("x-request-id", success.headers)
                for value in ("unknown.pdf", "trusted.txt", "../trusted.pdf", "%2e%2e%2ftrusted.pdf", "%252e%252e%252ftrusted.pdf"):
                    response = client.get(f"{prefix}/{value}")
                    self.assertEqual(response.status_code, 404)
                    self.assertNotIn(str(self.raw), response.text)
                    self.assertIn("x-request-id", response.headers)

    def test_legacy_and_v1_missing_registered_file_are_safe(self):
        self.pdf.unlink()
        with TestClient(self.app) as client:
            for prefix in ("/api/documents", "/api/v1/documents"):
                response = client.get(f"{prefix}/trusted.pdf")
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(str(self.raw), response.text)
