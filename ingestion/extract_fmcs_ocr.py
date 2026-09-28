"""Offline, deterministic OCR extraction for the two approved FMCS PDFs only.

This tool writes page sidecars and OCR-derived chunks beneath the supplied V4
output directory.  It never opens Chroma, contacts a provider, or fetches a
remote URL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from pypdf import PdfReader
try:
    from ingestion.fmcs_ocr_chunks import build_chunks
except ModuleNotFoundError:  # direct `python ingestion/extract_fmcs_ocr.py`
    from fmcs_ocr_chunks import build_chunks


ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "fmcs_application_form_v": {
        "incoming_path": "categories/Application Checklist/ApplicationFormV.pdf",
        "raw_path": "data/raw/fmcs/ApplicationFormV.pdf",
        "restriction": "FMCS only — do not generalize this form to domestic Scheme-I applications.",
        "ocr_required": True,
    },
    "fmcs_application_checklist": {
        "incoming_path": "categories/Application Checklist/Checklist_for_Application_for_BIS_Licence.pdf",
        "raw_path": "data/raw/fmcs/Checklist_for_Application_for_BIS_Licence.pdf",
        "restriction": "FMCS only — do not generalize this checklist to domestic Scheme-I applications.",
        "ocr_required": True,
    },
}
DPI = 300
LANGUAGE = "eng"
OEM = 1
PSM = 6
MIN_CONFIDENCE = 45.0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\x00", " ")).strip()


def load_approved_sources(manifest_path: Path) -> dict[str, dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_path = {row["incoming_path"]: row for row in manifest.get("records", [])}
    approved: dict[str, dict[str, Any]] = {}
    for source_id, target in TARGETS.items():
        row = by_path.get(target["incoming_path"])
        if not row or row.get("decision") != "active" or row.get("match") != "exact":
            raise ValueError(f"target is not an active exact approved source: {source_id}")
        if not row.get("incoming_sha256") or not row.get("canonical_official_url"):
            raise ValueError(f"target approval is incomplete: {source_id}")
        approved[source_id] = {**target, **row}
    return approved


def verified_source(source_id: str, raw_root: Path, approved: dict[str, dict[str, Any]]) -> tuple[Path, dict[str, Any]]:
    if source_id not in TARGETS:
        raise ValueError(f"unapproved source ID: {source_id}")
    record = approved.get(source_id)
    if record is None:
        raise ValueError(f"inactive or unapproved source ID: {source_id}")
    path = raw_root / record["raw_path"].removeprefix("data/raw/")
    if not path.is_file():
        raise FileNotFoundError(f"approved source is missing: {path}")
    actual = sha256_file(path)
    if actual != record["incoming_sha256"]:
        raise ValueError(f"SHA-256 mismatch for {source_id}: {actual}")
    return path, record


def command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def tool_versions(run: Callable[[list[str]], subprocess.CompletedProcess[str]] = command) -> dict[str, str]:
    tess = run(["tesseract", "--version"])
    ppm = run(["pdftoppm", "-v"])
    if tess.returncode or ppm.returncode:
        raise RuntimeError("local OCR tool version check failed")
    return {
        "tesseract": (tess.stdout or tess.stderr).splitlines()[0],
        "pdftoppm": (ppm.stderr or ppm.stdout).splitlines()[0],
    }


def embedded_text_pages(pdf_path: Path) -> list[str]:
    return [normalized_text(page.extract_text() or "") for page in PdfReader(pdf_path).pages]


def has_usable_embedded_text(pages: list[str]) -> bool:
    combined = " ".join(pages)
    letters = sum(char.isalpha() for char in combined)
    return len(combined) >= 160 and letters >= 100 and letters / max(len(combined), 1) >= 0.35


def parse_tsv(tsv: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for line in tsv.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) != 12:
            continue
        try:
            confidence = float(parts[10])
        except ValueError:
            continue
        text = normalized_text(parts[11])
        if text:
            rows.append({"text": text, "confidence": confidence})
    confidences = [row["confidence"] for row in rows if row["confidence"] >= 0]
    return rows, {
        "word_count": len(rows),
        "mean_confidence": round(sum(confidences) / len(confidences), 2) if confidences else 0.0,
        "minimum_confidence": round(min(confidences), 2) if confidences else 0.0,
        "maximum_confidence": round(max(confidences), 2) if confidences else 0.0,
    }


def reject_reason(line: str, confidence: float) -> str | None:
    value = normalized_text(line)
    if not value:
        return "empty"
    if confidence >= 0 and confidence < MIN_CONFIDENCE:
        return "low_confidence"
    if re.fullmatch(r"[_\-\.\s]{3,}", value):
        return "blank_field"
    if re.fullmatch(r"[☐☑□✓✔xX]", value):
        return "isolated_checkbox"
    if re.fullmatch(r"(?:s\.?\s*)?\d{1,4}", value, flags=re.IGNORECASE):
        return "standalone_serial_number"
    symbols = sum(not char.isalnum() and not char.isspace() for char in value)
    meaningful_short_label = value.lower() in {"name", "address", "signature", "date", "year", "part", "office", "factory"}
    if (len(value) < 5 and not meaningful_short_label) or symbols / len(value) > 0.55:
        return "symbol_dominated_noise"
    return None


def filter_lines(raw_text: str, tsv_rows: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, str]]]:
    word_confidence = {row["text"].lower(): row["confidence"] for row in tsv_rows}
    accepted: list[str] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in raw_text.splitlines():
        value = normalized_text(line)
        words = re.findall(r"[A-Za-z0-9]+", value.lower())
        confidences = [word_confidence.get(word, 100.0) for word in words]
        # A single uncertain short OCR token must not discard an otherwise
        # legible printed field label; no wording is corrected or inferred.
        confidence = sum(confidences) / len(confidences) if confidences else 100.0
        reason = reject_reason(value, confidence)
        key = value.lower()
        if reason:
            rejected.append({"text": value, "reason": reason})
        elif key not in seen:
            accepted.append(value)
            seen.add(key)
    return accepted, rejected


def remove_repeated_page_furniture(accepted: list[str], rejected: list[dict[str, str]], prior_lines: set[str]) -> tuple[list[str], list[dict[str, str]]]:
    retained = []
    for line in accepted:
        key = normalized_text(line).lower()
        if key in prior_lines:
            rejected.append({"text": line, "reason": "repeated_page_furniture"})
        else:
            retained.append(line)
            prior_lines.add(key)
    return retained, rejected


def detect_title(lines: list[str]) -> str:
    for line in lines:
        if len(line) >= 12 and (line.isupper() or "application" in line.lower() or "form" in line.lower()):
            return line
    return lines[0] if lines else ""


def ocr_page(pdf_path: Path, page_number: int, workdir: Path, run: Callable[[list[str]], subprocess.CompletedProcess[str]] = command) -> tuple[Path, str, str]:
    prefix = workdir / f"page-{page_number:04d}"
    rendered = run(["pdftoppm", "-f", str(page_number), "-l", str(page_number), "-r", str(DPI), "-png", str(pdf_path), str(prefix)])
    image = workdir / f"page-{page_number:04d}-{page_number}.png"
    if rendered.returncode or not image.is_file():
        raise RuntimeError(f"pdftoppm failed for page {page_number}: {rendered.stderr.strip()}")
    text = run(["tesseract", str(image), "stdout", "-l", LANGUAGE, "--oem", str(OEM), "--psm", str(PSM)])
    tsv = run(["tesseract", str(image), "stdout", "-l", LANGUAGE, "--oem", str(OEM), "--psm", str(PSM), "tsv"])
    if text.returncode or tsv.returncode:
        raise RuntimeError(f"tesseract failed for page {page_number}: {(text.stderr + tsv.stderr).strip()}")
    return image, text.stdout, tsv.stdout


def chunk_rows(source_id: str, record: dict[str, Any], sidecar: dict[str, Any], sidecar_path: Path) -> list[dict[str, Any]]:
    return build_chunks(source_id, record, sidecar, sidecar_path)


def extract_source(source_id: str, raw_root: Path, approved: dict[str, dict[str, Any]], output_dir: Path, run: Callable[[list[str]], subprocess.CompletedProcess[str]] = command) -> dict[str, Any]:
    pdf_path, record = verified_source(source_id, raw_root, approved)
    embedded = embedded_text_pages(pdf_path)
    # Both approved targets are explicitly bounded to the OCR path.  We still
    # inspect their embedded layer first so an unexpected source replacement is
    # observable, but their form/table serialization is not trusted as evidence.
    if has_usable_embedded_text(embedded) and not record.get("ocr_required", False):
        return {"source_id": source_id, "extraction_method": "embedded_text", "ocr_used": False, "page_count": len(embedded), "chunks": []}
    output_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = output_dir / "sidecars" / source_id
    pages_dir.mkdir(parents=True, exist_ok=True)
    versions = tool_versions(run)
    source_hash = sha256_file(pdf_path)
    sidecars: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    prior_accepted_lines: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="fmcs-ocr-") as temporary:
        workdir = Path(temporary)
        for page_number in range(1, len(embedded) + 1):
            image, raw, tsv = ocr_page(pdf_path, page_number, workdir, run)
            tsv_rows, summary = parse_tsv(tsv)
            accepted, rejected = filter_lines(raw, tsv_rows)
            accepted, rejected = remove_repeated_page_furniture(accepted, rejected, prior_accepted_lines)
            sidecar = {
                "accepted_lines": accepted, "detected_title": detect_title(accepted), "dpi": DPI, "extraction_method": "ocr",
                "filename": pdf_path.name, "language": LANGUAGE, "official_url": record["canonical_official_url"], "oem": OEM,
                "page_number": page_number, "psm": PSM, "raw_ocr_text": raw, "rejected_lines": rejected,
                "rendered_page_sha256": sha256_file(image), "source_id": source_id, "source_sha256": source_hash,
                "tool_versions": versions, "tsv_confidence_summary": summary, "normalized_ocr_text": normalized_text(raw),
            }
            sidecar_path = pages_dir / f"page-{page_number:04d}.json"
            sidecar_path.write_text(stable_json(sidecar), encoding="utf-8")
            sidecars.append(sidecar)
            chunks.extend(chunk_rows(source_id, record, sidecar, sidecar_path.relative_to(output_dir)))
    return {"source_id": source_id, "extraction_method": "ocr", "ocr_used": True, "page_count": len(sidecars), "sidecars": sidecars, "chunks": chunks}


def audit(result: list[dict[str, Any]]) -> dict[str, Any]:
    sources = []
    for item in result:
        pages = item.get("sidecars", [])
        sources.append({
            "source_id": item["source_id"], "pages": item["page_count"], "ocr_characters_per_page": [len(page["raw_ocr_text"]) for page in pages],
            "confidence_summary": [page["tsv_confidence_summary"] for page in pages], "accepted_line_count": sum(len(page["accepted_lines"]) for page in pages),
            "rejected_line_count": sum(len(page["rejected_lines"]) for page in pages), "chunk_count": len(item["chunks"]),
            "detected_title": next((page["detected_title"] for page in pages if page["detected_title"]), ""),
            "representative_accepted_lines": [line for page in pages for line in page["accepted_lines"]][:3],
            "representative_rejected_lines": [line for page in pages for line in page["rejected_lines"]][:3],
            "pages_needing_manual_review": [page["page_number"] for page in pages if page["tsv_confidence_summary"]["mean_confidence"] < 70 or not page["accepted_lines"]],
        })
    return {"audit_type": "fmcs_offline_ocr", "sources": sources, "network_calls": 0, "provider_calls": 0}


def markdown_audit(report: dict[str, Any]) -> str:
    lines = ["# FMCS OCR audit", "", "Offline local OCR only; no network, provider, or LLM calls.", ""]
    for source in report["sources"]:
        lines += [f"## {source['source_id']}", "", f"- Pages: {source['pages']}", f"- OCR characters per page: {source['ocr_characters_per_page']}", f"- Accepted/rejected lines: {source['accepted_line_count']}/{source['rejected_line_count']}", f"- Chunks: {source['chunk_count']}", f"- Detected title: {source['detected_title'] or '(none)'}", f"- Pages needing manual review: {source['pages_needing_manual_review']}", f"- Representative accepted: {source['representative_accepted_lines']}", f"- Representative rejected: {source['representative_rejected_lines']}", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True, choices=sorted(TARGETS))
    parser.add_argument("--manifest", type=Path, default=ROOT / "docs/corpus_v4_source_manifest.json")
    parser.add_argument("--raw-root", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed/generated_v4/fmcs_ocr")
    args = parser.parse_args(argv)
    source_ids = list(dict.fromkeys(args.source))
    approved = load_approved_sources(args.manifest)
    results = [extract_source(source_id, args.raw_root, approved, args.output_dir) for source_id in source_ids]
    if any(not result["ocr_used"] for result in results):
        raise RuntimeError("approved scanned FMCS source unexpectedly had usable embedded text; OCR output not written")
    chunks = [chunk for result in results for chunk in result["chunks"]]
    (args.output_dir / "chunks.jsonl").write_text("".join(json.dumps(chunk, ensure_ascii=False, sort_keys=True) + "\n" for chunk in chunks), encoding="utf-8")
    report = audit(results)
    (args.output_dir / "fmcs_ocr_audit.json").write_text(stable_json(report), encoding="utf-8")
    (args.output_dir / "fmcs_ocr_audit.md").write_text(markdown_audit(report), encoding="utf-8")
    print(stable_json({"sources": [{"source_id": item["source_id"], "pages": item["page_count"], "chunks": len(item["chunks"])} for item in results]}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
