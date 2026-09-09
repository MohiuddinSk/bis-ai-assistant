from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pypdf import PdfReader

try:
    import fitz
except ImportError:
    fitz = None

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
GENERATED_DIR = ROOT / "data" / "processed" / "generated_v2"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

SOURCE_CONFIG = {
    "product_manual_2026.pdf": ("manual", "current_candidate_needs_verification"),
    "Toy_QC_order.pdf": ("qco", "legal_rule_source"),
    "Toys-Quality-Control-Second-Amendment-Order-2020.pdf": ("amendment", "legal_rule_source"),
    "Toys-QCO-2024.pdf": ("amendment", "legal_rule_source"),
    "Toys-Extension.pdf": ("amendment", "legal_rule_source"),
    "Notification-of-Transition-Facilitation-Quality-Control-Order-2026.pdf": ("transition_order", "official_transition_source"),
    "10-steps-for-BIS-toy-certification.pdf": ("procedure", "guidance_needs_review"),
    "toys-faqs.pdf": ("faq", "guidance_needs_review"),
}


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_digest(path: Path) -> str:
    return digest(path.read_bytes())


def source_id(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", path.stem).strip("_")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def text_digest(text: str) -> str:
    return digest(normalize_space(text).lower().encode("utf-8"))


def language(text: str) -> str:
    if not (text or "").strip():
        return "unknown"
    hindi = bool(re.search(r"[\u0900-\u097f]", text))
    english = bool(re.search(r"[A-Za-z]", text))
    return "mixed" if hindi and english else "hi" if hindi else "en" if english else "unknown"


def quality(text: str) -> str:
    meaningful = re.sub(r"[^\w\u0900-\u097f]+", "", text or "", flags=re.UNICODE)
    return "empty" if not meaningful else "good" if len(meaningful) >= 80 else "low"


def meaningful_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def repeated_lines(raw_pages: list[str]) -> set[str]:
    counts: Counter[str] = Counter()
    for raw in raw_pages:
        counts.update({normalize_space(line) for line in raw.splitlines() if normalize_space(line)})
    return {line for line, count in counts.items() if count >= max(2, len(raw_pages) // 3) and len(line) <= 160}


def clean_text(raw: str, repeated: set[str]) -> str:
    kept = []
    for line in (raw or "").replace("\x00", "").splitlines():
        stripped = line.strip()
        if stripped and normalize_space(stripped) not in repeated:
            kept.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def extract_pages(path: Path) -> list[dict[str, Any]]:
    sid = source_id(path)
    source_hash = file_digest(path)
    reader = PdfReader(str(path))
    fallback = fitz.open(str(path)) if fitz is not None else None
    raw_pages = []
    for number, page in enumerate(reader.pages, 1):
        raw = page.extract_text() or ""
        if meaningful_length(raw) < 50 and fallback is not None:
            raw = fallback[number - 1].get_text("text", sort=True) or ""
        raw_pages.append(raw)
    if fallback is not None:
        fallback.close()
    repeated = repeated_lines(raw_pages)
    return [{
        "page_id": f"{sid}_p{number:03d}", "source_id": sid, "source_filename": path.name,
        "source_path": str(path.relative_to(ROOT)).replace("\\", "/"), "page_number": number,
        "raw_text": raw, "clean_text": clean_text(raw, repeated), "language": language(clean_text(raw, repeated)),
        "extraction_quality": quality(clean_text(raw, repeated)), "source_sha256": source_hash,
        "review_status": "needs_review",
    } for number, raw in enumerate(raw_pages, 1)]


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?।])\s+|(?=\n\s*(?:\d+(?:\.\d+)*[.)]|[A-Z][.)]))", text)
    return [normalize_space(part) for part in parts if normalize_space(part)]


def hard_split(text: str, limit: int = 1200) -> list[str]:
    return [text[start:start + limit].strip() for start in range(0, len(text), limit) if text[start:start + limit].strip()]


def chunk_page(text: str, target: int = 950, overlap: int = 150) -> list[str]:
    paragraphs = [normalize_space(part) for part in re.split(r"\n\s*\n+", text) if normalize_space(part)]
    units = []
    for paragraph in paragraphs:
        units.extend(hard_split(paragraph) if len(paragraph) > 1200 else sentences(paragraph) or [paragraph])
    result = []
    current = ""
    for unit in units:
        if len(unit) > 1200:
            if current:
                result.append(current.strip())
                current = ""
            result.extend(hard_split(unit))
            continue
        candidate = f"{current} {unit}".strip() if current else unit
        if current and len(candidate) > target:
            result.append(current.strip())
            current = f"{current[-overlap:].strip()} {unit}".strip()
        else:
            current = candidate
    if current:
        result.append(current.strip())
    return result


def make_chunk(text: str, page: dict[str, Any], source: dict[str, Any], index: int) -> dict[str, Any]:
    document = f"passage: {text}"
    metadata = {
        "chunk_type": "document_text", "source_id": source["source_id"], "source_filename": source["source_filename"],
        "source_path": source["source_path"], "source_type": source["source_type"], "source_status": source["source_status"],
        "page_start": page["page_number"], "page_end": page["page_number"], "section": "", "clause": "",
        "language": page["language"], "retrieval_enabled": True, "default_retrieval": True,
        "extraction_quality": page["extraction_quality"], "review_status": "needs_review", "char_count": len(document),
        "token_estimate": max(1, len(re.findall(r"\S+", text))), "text_sha256": digest(document.encode("utf-8")),
    }
    return {"id": f"doc_{source['source_id']}_p{page['page_number']:03d}_c{index:03d}", "document": document, "metadata": metadata}


def build_sources(paths: list[Path], pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for path in paths:
        sid = source_id(path)
        source_pages = [page for page in pages if page["source_id"] == sid]
        source_type, status = SOURCE_CONFIG[path.name]
        all_text = " ".join(page["clean_text"] for page in source_pages)
        result.append({
            "source_id": sid, "source_filename": path.name, "source_path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "source_type": source_type, "source_status": status, "default_retrieval": True, "retrieval_enabled": True,
            "page_count": len(source_pages), "extracted_page_count": sum(page["extraction_quality"] != "empty" for page in source_pages),
            "empty_page_count": sum(page["extraction_quality"] == "empty" for page in source_pages), "source_sha256": file_digest(path),
            "language": language(all_text), "notes": "pypdf first; PyMuPDF fallback for pages under 50 meaningful characters.",
        })
    return result


def duplicates(sources: list[dict[str, Any]], pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_files: dict[str, str] = {}
    seen_text: dict[str, str] = {}
    full_texts: dict[str, str] = {}
    result = []
    for source in sources:
        sid = source["source_id"]
        full_text = "\n".join(page["clean_text"] for page in pages if page["source_id"] == sid)
        full_texts[sid] = normalize_space(full_text).lower()
        for existing, value in seen_files.items():
            if value == source["source_sha256"]:
                result.append({"duplicate_source_id": sid, "canonical_source_id": existing, "duplicate_type": "exact_file", "similarity": 1.0})
        normalized_hash = text_digest(full_text)
        for existing, value in seen_text.items():
            if value == normalized_hash:
                result.append({"duplicate_source_id": sid, "canonical_source_id": existing, "duplicate_type": "same_text", "similarity": 1.0})
        seen_files[sid] = source["source_sha256"]
        seen_text[sid] = normalized_hash
    source_ids = list(full_texts)
    for index, left_id in enumerate(source_ids):
        for right_id in source_ids[index + 1:]:
            left_text = full_texts[left_id]
            right_text = full_texts[right_id]
            if len(left_text) < 200 or len(right_text) < 200:
                continue
            similarity = SequenceMatcher(None, left_text, right_text).ratio()
            if similarity >= 0.95 and not any(item["duplicate_source_id"] == right_id for item in result):
                result.append({
                    "duplicate_source_id": right_id,
                    "canonical_source_id": left_id,
                    "duplicate_type": "near_duplicate",
                    "similarity": round(similarity, 4),
                })
    return result


def structured_facts(source_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    facts = [
        ("fact_non_electric_standard", "For non-electric toys, the primary standard is IS 9873 Part 1; applicable secondary standards include IS 9873 Parts 2, 3, 4, 7 and 9.", "product_manual_2026.pdf"),
        ("fact_electric_standard", "For electric toys, the primary standard is IS 15644:2006, with applicable secondary standards from IS 9873.", "product_manual_2026.pdf"),
        ("fact_r_and_d_imports", "The 2024 amendment permits qualifying manufacturers to import up to 300 toy goods or related parts per financial year for research and development, subject to non-commercial disposal, records and declaration requirements.", "Toys-QCO-2024.pdf"),
        ("fact_handmade_exception", "The 2020 second amendment excludes goods made and sold by registered handicraft artisans and certain registered geographical-indication proprietors or authorised users; this is not a blanket exemption for all handmade toys.", "Toys-Quality-Control-Second-Amendment-Order-2020.pdf"),
        ("fact_application_documents", "An application for a new toy series uses the manufacturer declaration for change in scope and requires the series, toy description, category, sub-category, input source, age, standards and supporting model or material information.", "product_manual_2026.pdf"),
    ]
    result = []
    for fact_id, text, filename in facts:
        source = source_map[filename]
        document = f"passage: {text}"
        result.append({"id": fact_id, "document": document, "metadata": {
            "chunk_type": "structured_fact", "fact_type": "rule", "source_id": source["source_id"], "source_filename": filename,
            "source_path": source["source_path"], "source_type": source["source_type"], "source_status": source["source_status"],
            "page_start": 1, "page_end": 1, "section": "", "clause": "", "language": "en", "retrieval_enabled": True,
            "default_retrieval": True, "extraction_quality": "good", "review_status": "structured_record", "char_count": len(document),
            "token_estimate": len(text.split()), "text_sha256": digest(document.encode("utf-8")),
        }})
    return result


def main() -> None:
    paths = sorted(RAW_DIR.glob("*.pdf"), key=lambda path: path.name.lower())
    if {path.name for path in paths} != set(SOURCE_CONFIG):
        raise SystemExit("Raw PDF inventory does not match the configured eight sources")
    pages = [page for path in paths for page in extract_pages(path)]
    sources = build_sources(paths, pages)
    source_map = {source["source_filename"]: source for source in sources}
    chunks = []
    for page in pages:
        source = source_map[page["source_filename"]]
        chunks.extend(make_chunk(text, page, source, index) for index, text in enumerate(chunk_page(page["clean_text"]), 1))
    chunks.extend(structured_facts(source_map))
    seen_documents: set[str] = set()
    unique_chunks = []
    for chunk in chunks:
        document = chunk["document"]
        if document in seen_documents:
            continue
        seen_documents.add(document)
        unique_chunks.append(chunk)
    chunks = unique_chunks
    files = {
        "pages.jsonl": "\n".join(json.dumps(page, ensure_ascii=False) for page in pages) + "\n",
        "chunks.jsonl": "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n",
        "source_registry.json": json.dumps(sources, ensure_ascii=False, indent=2) + "\n",
        "duplicate_map.json": json.dumps(duplicates(sources, pages), ensure_ascii=False, indent=2) + "\n",
        "summary.json": json.dumps({"pdf_files_processed": len(paths), "total_pdf_pages": len(pages), "chunks_written": len(chunks)}, indent=2) + "\n",
    }
    for filename, content in files.items():
        (GENERATED_DIR / filename).write_text(content, encoding="utf-8")
    print(f"Processed PDFs: {len(paths)}")
    print(f"Processed pages: {len(pages)}")
    print(f"Wrote chunks: {len(chunks)}")
    print(f"Output directory: {GENERATED_DIR}")


if __name__ == "__main__":
    main()
