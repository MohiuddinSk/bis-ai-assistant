"""Read-only resolution of registered source PDFs."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path, PurePath
from urllib.parse import unquote

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data" / "raw"
REGISTRY_PATH = ROOT / "data" / "processed" / "generated_v3" / "source_registry.json"
CANDIDATE_PATH = ROOT / "data" / "processed" / "hallmarking_candidate_v1" / "evidence.json"


class SourceDocumentRegistry:
    def __init__(self, raw_root: Path = RAW_ROOT, registry_path: Path = REGISTRY_PATH, candidate_path: Path = CANDIDATE_PATH):
        self._raw_root = raw_root.resolve()
        entries = json.loads(registry_path.read_text(encoding="utf-8"))
        self._filenames = {
            entry["source_filename"]
            for entry in entries
            if isinstance(entry.get("source_filename"), str)
        }
        self._extra_paths: dict[str, Path] = {}
        if candidate_path.is_file():
            package = json.loads(candidate_path.read_text(encoding="utf-8"))
            if package.get("version") == "hallmarking_candidate_v1":
                for row in package.get("records", []):
                    if row.get("source_type") != "pdf":
                        continue
                    filename = row.get("source_filename")
                    expected_hash = row.get("source_sha256")
                    if not isinstance(filename, str) or self._plain_filename(filename) != filename:
                        continue
                    candidate = (self._raw_root / "jewellery" / filename).resolve()
                    if candidate.parent != (self._raw_root / "jewellery").resolve() or not candidate.is_file():
                        continue
                    if hashlib.sha256(candidate.read_bytes()).hexdigest() == expected_hash:
                        self._extra_paths[filename] = candidate

    @staticmethod
    def _plain_filename(value: str) -> str | None:
        decoded = value
        # Defend against double-encoded separators as well as ordinary URL decoding.
        for _ in range(3):
            next_value = unquote(decoded)
            if next_value == decoded:
                break
            decoded = next_value
        if not decoded or decoded != PurePath(decoded).name:
            return None
        if "/" in decoded or "\\" in decoded or decoded in {".", ".."}:
            return None
        return decoded

    def resolve(self, requested_filename: str) -> Path:
        filename = self._plain_filename(requested_filename)
        if filename is None or not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=404, detail="Source document not found.")
        if filename in self._extra_paths:
            return self._extra_paths[filename]
        if filename not in self._filenames:
            raise HTTPException(status_code=404, detail="Source document not found.")
        candidate = (self._raw_root / filename).resolve()
        if candidate.parent != self._raw_root or not candidate.is_file():
            raise HTTPException(status_code=404, detail="Source document not found.")
        return candidate
