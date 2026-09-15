"""Read-only integrity checks for the committed generated-v3 data contract."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIRECTORY = Path("data/processed/generated_v3")
MANIFEST_PATH = GENERATED_DIRECTORY / "embedding_manifest.json"
REGISTRY_PATH = GENERATED_DIRECTORY / "source_registry.json"
CHUNKS_PATH = GENERATED_DIRECTORY / "chunks.jsonl"
EXPECTED_MANIFEST = {
    "model": "intfloat/multilingual-e5-small",
    "model_revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
    "dimension": 384,
    "normalize_embeddings": True,
    "retrieval_chunk_count": 917,
}


class ArtifactError(ValueError):
    """A concise, safe-to-report data-contract failure."""


def _fail(message: str) -> None:
    raise ArtifactError(message)


def _read_json(path: Path, label: str) -> Any:
    if not path.is_file():
        _fail(f"missing {label}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _fail(f"invalid {label}")


def _validate_jsonl(path: Path) -> None:
    if not path.is_file():
        _fail("missing chunk artifact")
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                json.loads(line)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _fail("invalid chunk artifact")


def _safe_repository_path(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        _fail("invalid registry path")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in value:
        _fail("unsafe registry path")
    resolved_root = root.resolve()
    resolved_path = (root / Path(*candidate.parts)).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        _fail("unsafe registry path")
    return resolved_path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _chunk_sha256(path: Path) -> str:
    """Hash text chunks in the LF form committed by the manifest.

    Git may check this JSONL file out with CRLF on Windows.  The manifest was
    generated from LF bytes, so only CRLF sequences are normalized before
    hashing; binary source files continue through ``_sha256`` unchanged.
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def validate(root: Path = ROOT) -> None:
    """Validate committed artifact metadata without modifying repository files."""
    root = root.resolve()
    manifest = _read_json(root / MANIFEST_PATH, "manifest")
    registry = _read_json(root / REGISTRY_PATH, "source registry")
    chunks = root / CHUNKS_PATH
    _validate_jsonl(chunks)

    if not isinstance(manifest, dict):
        _fail("invalid manifest")
    for key, expected in EXPECTED_MANIFEST.items():
        value = manifest.get(key)
        if type(value) is not type(expected) or value != expected:
            _fail("manifest contract mismatch")
    chunk_hash = manifest.get("chunks_sha256")
    if not isinstance(chunk_hash, str) or len(chunk_hash) != 64:
        _fail("invalid chunk hash")
    if _chunk_sha256(chunks) != chunk_hash:
        _fail("chunk hash mismatch")

    if not isinstance(registry, list) or not registry:
        _fail("invalid source registry")
    identifiers: set[str] = set()
    paths: set[str] = set()
    for entry in registry:
        if not isinstance(entry, dict):
            _fail("invalid registry entry")
        source_id = entry.get("source_id")
        source_path = entry.get("source_path")
        expected_hash = entry.get("source_sha256")
        if not isinstance(source_id, str) or not source_id:
            _fail("invalid source identifier")
        if source_id in identifiers:
            _fail("duplicate source identifier")
        identifiers.add(source_id)
        source_file = _safe_repository_path(root, source_path)
        normalized_path = source_file.relative_to(root).as_posix()
        if normalized_path in paths:
            _fail("duplicate or invalid source path")
        paths.add(normalized_path)
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            _fail("invalid source hash")
        if not source_file.is_file():
            _fail("missing raw source")
        if _sha256(source_file) != expected_hash:
            _fail("raw source hash mismatch")


def main() -> int:
    try:
        validate()
    except ArtifactError as error:
        print(f"CI artifact check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
