"""Deterministic, page-local grouping and validation for FMCS OCR sidecars."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


MIN_CHARS = 40
MAX_CHARS = 850


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_heading(line: str) -> bool:
    letters = [char for char in line if char.isalpha()]
    return len(line) >= 10 and bool(letters) and all(char.isupper() for char in letters)


def is_item_start(line: str) -> bool:
    return bool(re.match(r"^\d{1,2}\s*[.|]", line))


def group_lines(lines: list[str]) -> list[list[str]]:
    """Keep OCR verbatim while joining related adjacent lines on one page."""
    groups: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        current_size = len("\n".join(current))
        boundary = current and (is_heading(line) or (is_item_start(line) and current_size >= MIN_CHARS))
        if boundary or current_size + len(line) + 1 > MAX_CHARS:
            groups.append(current)
            current = []
        current.append(line)
    if current:
        groups.append(current)
    # A short tail is usually a continuation or printed field label, not a
    # standalone retrieval unit.  Never merge across this page boundary.
    if len(groups) > 1 and len("\n".join(groups[-1])) < MIN_CHARS:
        groups[-2].extend(groups.pop())
    return groups


def meaningful(text: str) -> bool:
    letters = sum(char.isalpha() for char in text)
    symbols = sum(not char.isalnum() and not char.isspace() for char in text)
    return len(normalize(text)) >= MIN_CHARS and letters >= 20 and symbols / max(len(text), 1) <= 0.45


def stable_chunk_id(source_id: str, page: int, lines: list[str]) -> str:
    payload = f"{source_id}:{page}:" + "\n".join(lines)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_chunks(source_id: str, record: dict[str, Any], sidecar: dict[str, Any], sidecar_path: Path) -> list[dict[str, Any]]:
    chunks = []
    for lines in group_lines(sidecar["accepted_lines"]):
        text = "\n".join(lines)
        if not meaningful(text):
            continue
        chunk_id = stable_chunk_id(source_id, sidecar["page_number"], lines)
        metadata = {
            "source_id": source_id, "source_filename": sidecar["filename"], "source_sha256": sidecar["source_sha256"],
            "source_url": sidecar["official_url"], "page_start": sidecar["page_number"], "page_end": sidecar["page_number"],
            "category": "fmcs", "scope": "fmcs_only", "scheme_scope": "FMCS only", "status": "active",
            "authority": "authoritative", "extraction_method": "ocr", "sidecar_reference": sidecar_path.as_posix(),
            "confidence_indicator": sidecar["tsv_confidence_summary"]["mean_confidence"],
            "restriction": record["restriction"], "retrieval_enabled": True, "chunk_type": "ocr_form_group",
            "original_ocr_lines": "\n".join(lines),
        }
        chunks.append({"id": chunk_id, "document": "passage: " + text, "metadata": metadata})
    return chunks


def validate_chunk(chunk: dict[str, Any]) -> None:
    metadata = chunk["metadata"]
    required = ("source_id", "source_filename", "source_sha256", "source_url", "page_start", "page_end", "category", "scope", "authority", "status", "extraction_method", "sidecar_reference", "confidence_indicator", "restriction")
    if not all(metadata.get(key) not in (None, "") for key in required):
        raise ValueError("incomplete OCR chunk metadata")
    if metadata["category"] != "fmcs" or metadata["scope"] != "fmcs_only" or metadata["extraction_method"] != "ocr":
        raise ValueError("invalid FMCS OCR metadata")
    if "domestic" not in metadata["restriction"].lower() or metadata["page_start"] != metadata["page_end"]:
        raise ValueError("invalid OCR restriction or page provenance")
    if not meaningful(chunk["document"].removeprefix("passage: ")):
        raise ValueError("invalid noisy OCR chunk")
