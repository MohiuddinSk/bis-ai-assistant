"""Import invariants for dated official-directory snapshots."""

import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook
from lxml import html

from scripts import sync_bis_directories as sync


class DirectoryImportTests(unittest.TestCase):
    def test_lims_next_link_replaces_duplicate_page_parameter(self):
        document = html.fromstring(
            '<a href="/home/search_is_number/?is_number__doc_no=2062&page=2&page=3">Next</a>'
        )
        self.assertEqual(
            sync.next_page(document, "https://lims.bis.gov.in/home/search_is_number/?is_number__doc_no=2062&page=2"),
            "https://lims.bis.gov.in/home/search_is_number/?is_number__doc_no=2062&page=3",
        )

    def test_csv_and_json_metadata_keep_provenance_and_reject_unofficial_detail_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [
                {"identifier": "IS 456:2024", "title": "Verified title", "official_detail_url": "https://standards.bis.gov.in/record"},
                {"identifier": "IS 789:2025", "title": "Bad link", "official_detail_url": "https://example.com/record"},
            ]
            for extension in ("json", "csv"):
                source = root / f"official.{extension}"
                if extension == "json":
                    source.write_text(json.dumps(rows), encoding="utf-8")
                else:
                    import csv
                    with source.open("w", encoding="utf-8", newline="") as stream:
                        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                        writer.writeheader()
                        writer.writerows(rows)
                manifest = {"standards": {"path": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                                          "retrieved_at": "2026-09-30T00:00:00+00:00"}}
                with patch.object(sync, "ROOT", root):
                    records, counts = sync.parse_standards(manifest)
                self.assertEqual(counts["accepted"], 1)
                self.assertEqual(counts["rejected"], 1)
                self.assertEqual(records[0]["official_detail_url"], "https://standards.bis.gov.in/record")
                self.assertIn(extension.upper(), records[0]["provenance"])

    def test_excel_rejects_invalid_and_duplicate_rows_but_keeps_distinct_editions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["BIS published standards"])
            sheet.append(["Sl#", "Standard Number", "Date of Publish", "Title", "Type of Standard", "Degree of Equivalence"])
            sheet.append([1, "IS 123 (Part 2/Sec 1):2024", "2024-01-02", "First title", "Product", None])
            sheet.append([2, "IS 123 (Part 2/Sec 1):2025", None, "New edition", "Product", None])
            sheet.append([3, "IS 123 (Part 2/Sec 1):2024", None, "Duplicate", "Product", None])
            sheet.append([4, "IS 999:2025", None, None, "Product", None])
            source = root / "official.xlsx"
            workbook.save(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            manifest = {"standards": {"path": source.name, "sha256": digest, "retrieved_at": "2026-09-30T00:00:00+00:00"}}
            with patch.object(sync, "ROOT", root):
                records, counts = sync.parse_standards(manifest)
            self.assertEqual(counts["source_rows"], 4)
            self.assertEqual(counts["accepted"], 2)
            self.assertEqual(counts["rejected"], 2)
            self.assertEqual([row["edition_year"] for row in records], ["2024", "2025"])
            self.assertEqual(records[0]["part"], "2")
            self.assertEqual(records[0]["section"], "1")
            self.assertEqual(records[0]["source_publication_date"], "2024-01-02")
            self.assertIsNone(records[1]["source_publication_date"])
            self.assertEqual(records[0]["provenance"], "BIS Published Standards Excel export, row 3")

    def test_failed_refresh_does_not_replace_last_good_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "data" / "reference" / "bis_directories"
            directory.mkdir(parents=True)
            manifest_path = directory / "manifest.json"
            original = {"parser_version": "previous", "standards": {"sha256": "last-good"}, "sources": []}
            manifest_path.write_text(json.dumps(original), encoding="utf-8")
            source = root / "official.xlsx"
            source.write_bytes(b"PK\x03\x04sample")
            args = argparse.Namespace(standards_file=source, standards_url="https://standards.bis.gov.in/export.xlsx",
                                      max_lab_pages=1, max_scope_pages=1, delay=0, refresh=True)
            with patch.object(sync, "ROOT", root), patch.object(sync, "DIRECTORY", directory), \
                 patch.object(sync, "RAW", directory / "raw"), patch.object(sync, "MANIFEST", manifest_path), \
                 patch.object(sync, "snapshot", side_effect=RuntimeError("source unavailable")):
                with self.assertRaisesRegex(RuntimeError, "source unavailable"):
                    sync.acquire(args)
            self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8")), original)


if __name__ == "__main__":
    unittest.main()
