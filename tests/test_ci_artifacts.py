import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import check_ci_artifacts


class CiArtifactTests(unittest.TestCase):
    def make_fixture(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        generated = root / "data/processed/generated_v3"
        raw = root / "data/raw"
        generated.mkdir(parents=True)
        raw.mkdir(parents=True)
        source = raw / "example.pdf"
        source.write_bytes(b"synthetic pdf bytes")
        chunks = generated / "chunks.jsonl"
        chunks.write_text('{"id":"chunk-1"}\n', encoding="utf-8")
        manifest = {
            **check_ci_artifacts.EXPECTED_MANIFEST,
            "chunks_sha256": hashlib.sha256(chunks.read_bytes()).hexdigest(),
        }
        (generated / "embedding_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        registry = [{
            "source_id": "example",
            "source_path": "data/raw/example.pdf",
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }]
        (generated / "source_registry.json").write_text(json.dumps(registry), encoding="utf-8")
        return root

    def assert_invalid(self, root: Path) -> None:
        with self.assertRaises(check_ci_artifacts.ArtifactError):
            check_ci_artifacts.validate(root)

    def registry(self, root: Path) -> Path:
        return root / check_ci_artifacts.REGISTRY_PATH

    def test_valid_fixture_passes(self):
        check_ci_artifacts.validate(self.make_fixture())

    def test_missing_required_file_fails(self):
        root = self.make_fixture()
        (root / check_ci_artifacts.MANIFEST_PATH).unlink()
        self.assert_invalid(root)

    def test_malformed_json_and_jsonl_fail(self):
        root = self.make_fixture()
        self.registry(root).write_text("not json", encoding="utf-8")
        self.assert_invalid(root)
        root = self.make_fixture()
        (root / check_ci_artifacts.CHUNKS_PATH).write_text("{bad}\n", encoding="utf-8")
        self.assert_invalid(root)

    def test_wrong_collection_count_fails(self):
        root = self.make_fixture()
        path = root / check_ci_artifacts.MANIFEST_PATH
        content = json.loads(path.read_text(encoding="utf-8"))
        content["retrieval_chunk_count"] = 916
        path.write_text(json.dumps(content), encoding="utf-8")
        self.assert_invalid(root)

    def test_wrong_embedding_contract_values_fail(self):
        for key, value in (("model", "other"), ("model_revision", "0" * 40),
                           ("dimension", 1), ("normalize_embeddings", False)):
            root = self.make_fixture()
            path = root / check_ci_artifacts.MANIFEST_PATH
            content = json.loads(path.read_text(encoding="utf-8"))
            content[key] = value
            path.write_text(json.dumps(content), encoding="utf-8")
            self.assert_invalid(root)

    def test_chunk_hash_mismatch_fails(self):
        root = self.make_fixture()
        (root / check_ci_artifacts.CHUNKS_PATH).write_text('{"id":"changed"}\n', encoding="utf-8")
        self.assert_invalid(root)

    def test_lf_and_crlf_chunks_match_the_manifest_hash(self):
        root = self.make_fixture()
        chunks = root / check_ci_artifacts.CHUNKS_PATH
        expected_hash = json.loads((root / check_ci_artifacts.MANIFEST_PATH).read_text(encoding="utf-8"))["chunks_sha256"]
        self.assertEqual(check_ci_artifacts._chunk_sha256(chunks), expected_hash)
        chunks.write_bytes(chunks.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(check_ci_artifacts._chunk_sha256(chunks), expected_hash)
        check_ci_artifacts.validate(root)

    def test_missing_or_changed_raw_pdf_fails(self):
        root = self.make_fixture()
        (root / "data/raw/example.pdf").unlink()
        self.assert_invalid(root)
        root = self.make_fixture()
        (root / "data/raw/example.pdf").write_bytes(b"changed")
        self.assert_invalid(root)

    def test_duplicate_identifiers_and_paths_fail(self):
        for duplicate_field in ("source_id", "source_path"):
            root = self.make_fixture()
            path = self.registry(root)
            entry = json.loads(path.read_text(encoding="utf-8"))[0]
            duplicate = dict(entry)
            if duplicate_field == "source_id":
                duplicate["source_path"] = "data/raw/another.pdf"
                (root / "data/raw/another.pdf").write_bytes(b"another")
                duplicate["source_sha256"] = hashlib.sha256(b"another").hexdigest()
            path.write_text(json.dumps([entry, duplicate]), encoding="utf-8")
            self.assert_invalid(root)

    def test_empty_registry_and_wrong_manifest_types_fail(self):
        root = self.make_fixture()
        self.registry(root).write_text("[]", encoding="utf-8")
        self.assert_invalid(root)
        root = self.make_fixture()
        path = root / check_ci_artifacts.MANIFEST_PATH
        content = json.loads(path.read_text(encoding="utf-8"))
        content["normalize_embeddings"] = 1
        path.write_text(json.dumps(content), encoding="utf-8")
        self.assert_invalid(root)

    def test_absolute_and_traversal_paths_fail(self):
        for unsafe_path in ("/tmp/example.pdf", "data/raw/../example.pdf", "C:\\example.pdf"):
            root = self.make_fixture()
            path = self.registry(root)
            registry = json.loads(path.read_text(encoding="utf-8"))
            registry[0]["source_path"] = unsafe_path
            path.write_text(json.dumps(registry), encoding="utf-8")
            self.assert_invalid(root)

    def test_checker_performs_no_writes(self):
        root = self.make_fixture()
        before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
        check_ci_artifacts.validate(root)
        after = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_production_repository_artifacts_pass(self):
        check_ci_artifacts.validate()


if __name__ == "__main__":
    unittest.main()
