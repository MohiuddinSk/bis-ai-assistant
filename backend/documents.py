"""Read-only resolution of registered source PDFs."""

from __future__ import annotations

import json
from pathlib import Path, PurePath
from urllib.parse import unquote

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data" / "raw"
REGISTRY_PATH = ROOT / "data" / "processed" / "generated_v3" / "source_registry.json"


class SourceDocumentRegistry:
    def __init__(self, raw_root: Path = RAW_ROOT, registry_path: Path = REGISTRY_PATH):
        self._raw_root = raw_root.resolve()
        entries = json.loads(registry_path.read_text(encoding="utf-8"))
        self._filenames = {
            entry["source_filename"]
            for entry in entries
            if isinstance(entry.get("source_filename"), str)
        }

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
        if filename not in self._filenames:
            raise HTTPException(status_code=404, detail="Source document not found.")
        candidate = (self._raw_root / filename).resolve()
        if candidate.parent != self._raw_root or not candidate.is_file():
            raise HTTPException(status_code=404, detail="Source document not found.")
        return candidate
