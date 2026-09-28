"""Non-destructive Phase 1.5 review for an incoming corpus.

This module intentionally never copies, deletes, indexes, or changes source
documents.  It produces a review record from bounded local extraction only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from corpus_audit import MIME, normalized_category, sha256


ROOT = Path(__file__).resolve().parents[1]
# This is an audit preview, not corpus extraction.  A small page/text bound keeps
# the operation deterministic and avoids treating a long OCR PDF as executable work.
TEXT_LIMIT = 24_000
PDF_PAGE_LIMIT = 6


def normalize_text(value: str) -> str:
    """Return a conservative comparison form; never use it as published text."""
    value = value.casefold().replace("\u00ad", "")
    value = re.sub(r"\s+", " ", value)
    return re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).strip()


def normalized_text_hash(value: str) -> str:
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()


def near_duplicate_similarity(left: str, right: str) -> float:
    """Deterministic, bounded textual similarity for human review, not authority."""
    return round(SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio(), 4)


def _pdf_extract(path: Path) -> tuple[str, int | None, str | None]:
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return "", None, "unsupported_extractor"
    try:
        reader = PdfReader(str(path))
        parts: list[str] = []
        remaining = TEXT_LIMIT
        for page in reader.pages[:PDF_PAGE_LIMIT]:
            if remaining <= 0:
                break
            text = page.extract_text() or ""
            parts.append(text[:remaining])
            remaining -= len(parts[-1])
        return "\n".join(parts), len(reader.pages), None
    except Exception as exc:  # extraction errors are data, not a reason to retry unsafely
        return "", None, f"unreadable_pdf:{type(exc).__name__}"


def inspect_docx(path: Path) -> tuple[str, int | None, str | None]:
    """Safely inspect a DOCX without opening links, macros, or embedded objects.

    A valid Office ZIP remains *secondary/unverified* even if python-docx is not
    installed.  This keeps "unsupported extractor" distinct from corruption.
    """
    try:
        if not zipfile.is_zipfile(path):
            return "", None, "corrupt_document:not_zip"
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                return "", None, "corrupt_document:missing_word_parts"
    except (OSError, zipfile.BadZipFile) as exc:
        return "", None, f"corrupt_document:{type(exc).__name__}"

    try:
        from docx import Document
    except ModuleNotFoundError:
        return "", None, "unsupported_extractor:python_docx_unavailable"

    try:
        document = Document(str(path))
        # Paragraph text only: no relationships, hyperlinks, macros, or objects are followed.
        parts: list[str] = []
        size = 0
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            parts.append(text)
            size += len(text) + 1
            if size >= TEXT_LIMIT:
                break
        return "\n".join(parts)[:TEXT_LIMIT], None, None
    except Exception as exc:
        return "", None, f"corrupt_document:{type(exc).__name__}"


def bounded_extract(path: Path) -> tuple[str, int | None, str | None]:
    if path.suffix.casefold() == ".pdf":
        return _pdf_extract(path)
    if path.suffix.casefold() == ".docx":
        return inspect_docx(path)
    return "", None, "unsupported_type"


def _identifiers(text: str) -> list[str]:
    patterns = (
        r"\bIS\s*[-:]?\s*\d{3,6}(?:\s*(?:Part|Pt\.?|/)[\s-]*\d+)?\b",
        r"\b(?:Quality Control|Transition Facilitation)[^\n]{0,80}Order\b",
        r"\bPM\s*/?\s*IS\s*\d{3,6}\s*/?\s*\d+\b",
    )
    values: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = re.sub(r"\s+", " ", match.group(0)).strip()
            if value not in values:
                values.append(value)
    return values[:20]


def _visible_dates(text: str) -> list[str]:
    patterns = (r"\b\d{1,2}[./-]\d{1,2}[./-](?:20)?\d{2}\b", r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}\b")
    found: list[str] = []
    for pattern in patterns:
        for value in re.findall(pattern, text, re.IGNORECASE):
            if value not in found:
                found.append(value)
    return found[:12]


def _visible_authority(text: str) -> str:
    folded = text.casefold()
    if "bureau of indian standards" in folded:
        return "BIS named in extracted document text (requires primary-source verification)"
    if "government of india" in folded or "ministry of commerce" in folded or "dpiit" in folded:
        return "Government/DPIIT named in extracted document text (requires primary-source verification)"
    return "No issuing authority established by bounded extracted text"


def _historical_reason(relative_path: str, text: str) -> tuple[str | None, str | None]:
    folded = text.casefold()
    name = relative_path.casefold()
    if "pm-9873" in name or "productmanualupadate-9873" in name or name.endswith("historical.pdf"):
        return ("October 2023/February 2023 PM-9873 version; current registry contains product_manual_2026.pdf.", "data/raw/product_manual_2026.pdf")
    if "revised-guidelines-for-jewellers-jan-24" in name:
        return ("January 2024 jewellery guideline; incoming 2026 guideline appears later, pending content/provenance confirmation.", "Guidelines-for-Jewellers.pdf")
    if "second-amendment-order-2020" in name:
        return ("2020 amendment is historical by visible order date; current controlling order must be confirmed from official source.", None)
    if "toys-qco-2024" in name:
        return ("2024 QCO version is dated and requires confirmation against later notifications/orders.", None)
    return None, None


def _classification(relative_path: str, suffix: str, error: str | None, historical: str | None, exact: bool) -> str:
    if error and error.startswith("corrupt_document") or error and error.startswith("unreadable_pdf"):
        return "unreadable/quarantined"
    if historical:
        return "historical/superseded"
    if exact:
        return "exact duplicate"
    if suffix == ".docx":
        return "structured/team-created secondary source"
    return "new candidate"


def _eligibility(classification: str, authority: str, error: str | None, relative_path: str) -> tuple[str, str]:
    if classification == "exact duplicate":
        return "exclude", "Identical content is already represented; retain only its existing canonical source."
    if classification == "unreadable/quarantined":
        return "quarantine", "Do not retrieve or ingest until a safe, readable primary replacement is supplied."
    if classification == "historical/superseded":
        return "historical retrieval only (disabled by default)", "Requires an explicit historical flag and user-facing date/status warning."
    if classification == "structured/team-created secondary source":
        return "secondary retrieval only (pending provenance)", "Valid DOCX status does not establish primary authority; primary citations must be verified first."
    if "No issuing authority" in authority:
        return "quarantine pending provenance", "Bounded text does not establish an issuing authority."
    if any(term in relative_path.casefold() for term in ("lab", "fees")):
        return "active with freshness warning (pending human approval)", "Official-looking time-sensitive material needs source URL/date confirmation and a freshness warning."
    return "active authoritative retrieval (pending human approval)", "Visible issuer evidence is promising but must be confirmed against an official primary source before activation."


def _relation(row: dict[str, Any], all_rows: list[dict[str, Any]]) -> str:
    related = []
    for other in all_rows:
        if other is row:
            continue
        if other["normalized_text_hash"] == row["normalized_text_hash"] and row["normalized_text_hash"] != hashlib.sha256(b"").hexdigest():
            related.append(f"normalized-text duplicate of {other['original_relative_path']}")
        elif row["text"] and other["text"]:
            similarity = near_duplicate_similarity(row["text"], other["text"])
            if similarity >= 0.82:
                related.append(f"probable text/version variant ({similarity}) of {other['original_relative_path']}")
    return "; ".join(related[:3]) or "No high-similarity incoming text relationship detected."


def _semantic_comparisons(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Record the specifically requested version comparisons for a human reviewer."""
    def choose(fragment: str) -> dict[str, Any] | None:
        return next((row for row in rows if fragment.casefold() in row["original_relative_path"].casefold()), None)

    groups = [
        ("10-step guide variants", ["final2", "categories/toys/10-steps-for-bis-toy-certification.pdf"]),
        ("jewellery guideline variants", ["guidelines-for-jewellers.pdf", "revised-guidelines-for-jewellers-jan-24"]),
        ("October 2023 PM-9873 variants", ["1 pm-9873-oct-2023", "productmanualupadate-9873-oct-2023", "historical.pdf"]),
        ("2026 transition variants", ["transition_2026_transition control", "notification-of-transition"]),
        ("Toys QCO/order variants", ["toys-qco-2024", "toy_qc_order", "second-amendment-order-2020"]),
    ]
    records: list[dict[str, Any]] = []
    for label, fragments in groups:
        selected = [row for fragment in fragments if (row := choose(fragment)) is not None]
        if len(selected) < 2:
            continue
        base = selected[0]
        records.append({
            "comparison": label,
            "files": [row["original_relative_path"] for row in selected],
            "normalized_text_hashes": [row["normalized_text_hash"] for row in selected],
            "page_counts": [row["page_count"] for row in selected],
            "identifiers": [row["standard_order_scheme_identifiers"] for row in selected],
            "similarity_to_first": [1.0] + [near_duplicate_similarity(base["text"], row["text"]) for row in selected[1:]],
            "review_note": "Similarity supports a version/duplicate review only; it does not establish authority or currentness.",
        })
    return records


def review(incoming: Path, raw: Path, registry: Path | None = None) -> dict[str, Any]:
    def source_label(path: Path) -> str:
        try:
            return str(path.relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            return path.name

    raw_hashes = {sha256(path): source_label(path) for path in raw.rglob("*") if path.is_file()}
    registry = registry or raw.parent / "processed" / "generated_v3" / "source_registry.json"
    registry_hashes: dict[str, str] = {}
    if registry.is_file():
        try:
            for entry in json.loads(registry.read_text(encoding="utf-8")):
                digest = entry.get("source_sha256")
                if digest:
                    registry_hashes[digest] = str(entry.get("source_filename") or "registry source")
        except (OSError, ValueError, TypeError):
            # A registry parsing issue is reported through individual unresolved
            # provenance review, never used to overwrite or repair the registry.
            pass
    incoming_files = sorted(path for path in incoming.rglob("*") if path.is_file() and path.suffix.casefold() in MIME)
    incoming_hashes: dict[str, list[Path]] = defaultdict(list)
    for path in incoming_files:
        incoming_hashes[sha256(path)].append(path)

    rows: list[dict[str, Any]] = []
    for path in incoming_files:
        relative = str(path.relative_to(incoming)).replace("\\", "/")
        digest = sha256(path)
        text, pages, error = bounded_extract(path)
        historical, replacement = _historical_reason(relative, text)
        # Only an existing raw corpus match excludes a source outright.  Repeated
        # incoming historical versions are still reviewable historical records.
        exact = digest in raw_hashes or digest in registry_hashes
        authority = _visible_authority(text)
        classification = _classification(relative, path.suffix.casefold(), error, historical, exact)
        eligibility, eligibility_reason = _eligibility(classification, authority, error, relative)
        rows.append({
            "original_relative_path": relative,
            "filename": path.name,
            "category": normalized_category(path, incoming),
            "mime_type": MIME[path.suffix.casefold()],
            "size_bytes": path.stat().st_size,
            "sha256": digest,
            "page_count": pages,
            "detected_title": next((line.strip() for line in text.splitlines() if line.strip()), ""),
            "standard_order_scheme_identifiers": _identifiers(text),
            "visible_dates": _visible_dates(text),
            "authority": authority,
            "currentness": "historical/superseded" if historical else ("unresolved" if classification in {"new candidate", "structured/team-created secondary source"} else classification),
            "classification": classification,
            "replacement": replacement or raw_hashes.get(digest) or registry_hashes.get(digest),
            "extraction_quality": error or ("bounded text extracted" if text else "no extractable text"),
            "table_ocr_risk": "high" if any(token in text.casefold() for token in ("column", "-do-", "left to right")) else "unknown/needs visual review",
            "proposed_active_retrieval_eligibility": eligibility,
            "freshness_warning": "Confirm currentness/source before relying on this time-sensitive document." if "freshness" in eligibility or historical else "None proposed until approval.",
            "reason": eligibility_reason if not historical else historical,
            "unresolved_question": "Which official URL or primary registry entry establishes authority and currentness?" if eligibility.startswith("active") or classification == "new candidate" else ("Which primary sources and authorship establish this structured file?" if path.suffix.casefold() == ".docx" else "None"),
            "text": text,
            "normalized_text_hash": normalized_text_hash(text),
        })
    comparisons = _semantic_comparisons(rows)
    for row in rows:
        row["duplicate_version_relationship"] = _relation(row, rows)
    for row in rows:
        row.pop("text")
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["classification"]] += 1
    return {
        "scope": "Phase 1.5 provenance, version, and content-quality review only; no ingestion or indexing performed.",
        "total_files": len(rows),
        "classification_counts": dict(sorted(counts.items())),
        "recommended_approvals": [row["original_relative_path"] for row in rows if row["proposed_active_retrieval_eligibility"].startswith("active")],
        "unresolved_provenance_questions": [row["original_relative_path"] for row in rows if row["unresolved_question"] != "None"],
        "semantic_duplicate_version_comparisons": comparisons,
        "files": rows,
    }


def write_reports(report: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Incoming Drive corpus review — 2026-09-28", "", report["scope"], "", "## Summary", ""]
    for key, value in report["classification_counts"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Proposed approvals requiring human confirmation", ""])
    lines.extend([f"- `{path}`" for path in report["recommended_approvals"]] or ["- None automatically approved."])
    lines.extend(["", "## Per-file review", "", "| File | Classification | Authority | Currentness | Eligibility |", "| --- | --- | --- | --- | --- |"])
    for row in report["files"]:
        lines.append(f"| `{row['original_relative_path']}` | {row['classification']} | {row['authority']} | {row['currentness']} | {row['proposed_active_retrieval_eligibility']} |")
    lines.extend(["", "No source files, raw registry, generated corpus, Chroma collection, or evaluation fixture was changed."])
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incoming", type=Path, default=ROOT / "data" / "incoming" / "drive_2026-09-28")
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--json", type=Path, default=ROOT / "docs" / "incoming_drive_2026-09-28_review.json")
    parser.add_argument("--markdown", type=Path, default=ROOT / "docs" / "incoming_drive_2026-09-28_review.md")
    args = parser.parse_args()
    report = review(args.incoming, args.raw)
    write_reports(report, args.json, args.markdown)


if __name__ == "__main__":
    main()
