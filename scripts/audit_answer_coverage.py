"""Read-only coverage audit for deterministic BIS guidance.

This diagnostic intentionally calls the production retrieval merge and evidence
planner, but supplies no generation provider.  It is for evidence-gap analysis,
not for changing the answer path or the index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Direct execution makes ``scripts/`` the first import location.  Add this
# repository's root before importing project packages; this stays local to the
# diagnostic and does not require PYTHONPATH or an editable installation.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.chat_service import ChatService, TrustedEvidence
from backend.generation import ProviderUnavailableError
from backend.question_understanding import understand_question
from backend.retrieval_provider import LocalChromaRetriever, RetrievalHit
from backend.schemas import ChatRequest

PROTECTED_PATHS = ("data/raw", "data/processed", "data/chroma", "evaluation")
QUALITY_RATINGS = frozenset({"GOOD", "USABLE_BUT_THIN", "VAGUE", "UNSUPPORTED", "CORRECTLY_LIMITED"})
CAUSE_CODES = frozenset({
    "SOURCE_ABSENT", "EXTRACTION_MISSING", "INDEX_MISSING", "RETRIEVAL_MISS",
    "RANKING_MISS", "PLANNER_DROPPED", "TEMPLATE_REDUCED", "CORRECT_LIMITATION",
})


@dataclass(frozen=True)
class FactCheck:
    name: str
    terms: tuple[str, ...]
    limitation: bool = False


@dataclass(frozen=True)
class AuditQuestion:
    identifier: str
    question: str
    facts: tuple[FactCheck, ...]


def _facts(*items: tuple[str, tuple[str, ...], bool]) -> tuple[FactCheck, ...]:
    return tuple(FactCheck(*item) for item in items)


AUDIT_QUESTIONS = (
    AuditQuestion("Q01", "Which standard applies to a battery-operated toy?", _facts(
        ("primary standard", ("is 15644",), False), ("secondary standards", ("is 9873", "where applicable"), False),
        ("conditional applicability", ("applic",), False), ("next action", ("next", "verify"), False))),
    AuditQuestion("Q02", "Explain IS 15644 in simple words.", _facts(
        ("standard identity", ("is 15644",), False), ("electric-toy role", ("electric", "primary"), False),
        ("applicability condition", ("applic",), False), ("relationship", ("is 9873",), False))),
    AuditQuestion("Q03", "When does IS 15644 apply?", _facts(
        ("standard identity", ("is 15644",), False), ("applicability", ("applic", "electric"), False),
        ("condition", ("where", "may", "verify"), False))),
    AuditQuestion("Q04", "Explain IS 9873 Part 1 in simple words.", _facts(
        ("standard identity", ("is 9873 part 1",), False), ("non-electric role", ("non-electric", "primary"), False),
        ("applicability", ("applic",), False))),
    AuditQuestion("Q05", "Explain IS 9873 Part 2 in simple words.", _facts(
        ("standard identity", ("is 9873 part 2",), False), ("secondary role", ("secondary", "where applicable"), False),
        ("scope or purpose", ("scope", "appl", "require"), False))),
    AuditQuestion("Q06", "Compare IS 15644 with IS 9873 Part 1.", _facts(
        ("IS 15644 role", ("is 15644", "electric"), False), ("IS 9873 Part 1 role", ("is 9873 part 1", "non-electric"), False),
        ("comparison limitation", ("not established", "cannot", "verify"), True))),
    AuditQuestion("Q07", "What documents are required to add a new toy series?", _facts(
        ("declaration", ("declaration",), False), ("series details", ("details", "series"), False),
        ("scope or fee condition", ("scope", "fee"), False), ("partial-list limitation", ("partial", "verify", "indexed"), True))),
    AuditQuestion("Q08", "Are all handmade toys exempt from BIS certification?", _facts(
        ("direct conditional answer", ("may apply only", "not all", "not automatically"), False),
        ("artisan manufacture and sale", ("manufactured", "sold", "artisan"), False),
        ("registration", ("registered", "development commissioner", "handicrafts"), False),
        ("handmade-alone limit", ("handmade", "alone", "insufficient"), False))),
    AuditQuestion("Q09", "What does the 2026 transition order allow?", _facts(
        ("operative permission", ("permit", "allow", "grant"), False), ("conditions", ("condition", "subject", "where"), False),
        ("limitation", ("does not", "verify", "not establish"), True))),
    AuditQuestion("Q10", "What are the steps to obtain BIS certification for a toy?", _facts(
        ("portal", ("manakonline",), False), ("standard selection", ("indian standard", "standard"), False),
        ("application details", ("raw material", "detail"), False), ("test facilities", ("test facilit",), False))),
    AuditQuestion("Q11", "Which IS 9873 parts may apply to a battery-operated toy?", _facts(
        ("battery/electric route", ("battery", "electric"), False), ("IS 9873", ("is 9873",), False),
        ("conditional language", ("may", "where applicable"), False))),
    AuditQuestion("Q12", "What should a manufacturer do after identifying the applicable toy standard?", _facts(
        ("immediate action", ("next", "application", "manakonline"), False), ("conditional limitation", ("verify", "where applicable", "indexed"), True))),
)


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def safe_excerpt(value: str, limit: int = 220) -> str:
    """Return a bounded, printable diagnostic excerpt without identifiers/config."""
    collapsed = re.sub(r"\s+", " ", value).strip()
    return collapsed[:limit].rstrip() + ("…" if len(collapsed) > limit else "")


def _matches(text: str, check: FactCheck) -> bool:
    normalized = normalize(text)
    return all(term in normalized for term in check.terms)


def _snapshot(paths: Iterable[str] = PROTECTED_PATHS) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in paths:
        root = ROOT / relative
        if not root.exists():
            continue
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result[path.relative_to(ROOT).as_posix()] = digest
    return result


def _safe_metadata(hit: RetrievalHit | object) -> dict[str, object]:
    """Normalize public provider hits and service retrieval results safely."""
    metadata = getattr(hit, "metadata", {})
    if not isinstance(metadata, dict):
        metadata = dict(metadata)
    return {
        "chunk_id": getattr(hit, "chunk_id"),
        "source_filename": getattr(hit, "source_filename", metadata.get("source_filename")),
        "page_start": getattr(hit, "page_start", metadata.get("page_start")),
        "page_end": getattr(hit, "page_end", metadata.get("page_end")),
        "distance": round(float(getattr(hit, "distance")), 6),
        "excerpt": safe_excerpt(getattr(hit, "text")),
    }


def _processed_texts() -> list[str]:
    texts: list[str] = []
    for path in sorted((ROOT / "data/processed").rglob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                for key in ("text", "document", "content"):
                    value = row.get(key)
                    if isinstance(value, str):
                        texts.append(value)
                        break
    return texts


def _raw_pdf_texts() -> tuple[list[str], bool]:
    """Read PDFs only when the already-installed PDF reader is available."""
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError:
        return [], False
    texts: list[str] = []
    for path in sorted((ROOT / "data/raw").glob("*.pdf")):
        try:
            reader = PdfReader(str(path))
            texts.extend(page.extract_text() or "" for page in reader.pages)
        except Exception:
            # A damaged/unsupported PDF must not make the diagnostic mutate or fail.
            continue
    return texts, True


def _normalized_text_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def _identity_key(hit: RetrievalHit) -> tuple[object, ...]:
    """A source/page/chunk identity that does not mistake split chunks for copies."""
    metadata = hit.metadata
    return (
        metadata.get("source_filename"), metadata.get("page_start"), metadata.get("page_end"),
        metadata.get("chunk_type"), metadata.get("text_sha256") or _normalized_text_hash(hit.text),
    )


def _duplicate_count(values: Iterable[object]) -> tuple[int, int]:
    counts: dict[object, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    groups = sum(1 for count in counts.values() if count > 1)
    records = sum(count - 1 for count in counts.values() if count > 1)
    return groups, records


def _collection_inventory() -> list[dict[str, object]]:
    """Read Chroma collection names/counts without opening or modifying a collection."""
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=str(ROOT / "data/chroma"), settings=Settings(anonymized_telemetry=False),
    )
    collections = client.list_collections()
    return sorted(
        ({"name": collection.name, "count": int(collection.count())} for collection in collections),
        key=lambda item: str(item["name"]),
    )


def index_metrics(indexed: Iterable[RetrievalHit]) -> dict[str, int]:
    """Pure deterministic duplicate metrics, suitable for diagnostic contract tests."""
    rows = list(indexed)
    text_groups, duplicate_text_records = _duplicate_count(_normalized_text_hash(row.text) for row in rows)
    identity_groups, duplicate_identity_records = _duplicate_count(_identity_key(row) for row in rows)
    return {
        "collection_count": len(rows),
        "unique_ids": len({row.chunk_id for row in rows}),
        "unique_normalized_text_hashes": len({_normalized_text_hash(row.text) for row in rows}),
        "duplicate_normalized_text_groups": text_groups,
        "duplicate_normalized_text_records": duplicate_text_records,
        "unique_source_page_chunk_identities": len({_identity_key(row) for row in rows}),
        "duplicate_source_page_chunk_identity_groups": identity_groups,
        "duplicate_source_page_chunk_identity_records": duplicate_identity_records,
    }


def index_integrity(indexed: Iterable[RetrievalHit]) -> dict[str, object]:
    """Calculate deterministic, read-only metrics for the active index rows."""
    rows = list(indexed)
    metrics = index_metrics(rows)
    manifest = json.loads((ROOT / "data/processed/generated_v3/embedding_manifest.json").read_text(encoding="utf-8"))
    collections = _collection_inventory()
    active_name = manifest["collection_name"]
    active_count = next((item["count"] for item in collections if item["name"] == active_name), None)
    if active_count != metrics["collection_count"] or int(manifest["retrieval_chunk_count"]) != metrics["collection_count"]:
        raise RuntimeError("Active collection and immutable retrieval manifest disagree")
    return {**metrics,
        "chroma_directory": "data/chroma",
        "production_collection": active_name,
        "all_collections": collections,
        "dataset_version": manifest["dataset_version"],
        "embedding_model": manifest["model"],
        "embedding_revision": manifest["model_revision"],
        "manifest_retrieval_chunk_count": int(manifest["retrieval_chunk_count"]),
    }


def _classify(check: FactCheck, answer: str, selected: list[TrustedEvidence], retrieved: list[RetrievalHit],
              ranked_candidates: list[RetrievalHit], indexed: list[RetrievalHit], processed: list[str],
              raw: list[str], raw_checked: bool) -> str:
    if _matches(answer, check):
        return "INCLUDED"
    if any(_matches(item.text, check) for item in selected):
        return "TEMPLATE_REDUCED"
    if any(_matches(item.text, check) for item in retrieved):
        return "PLANNER_DROPPED"
    if any(_matches(item.text, check) for item in ranked_candidates):
        return "RANKING_MISS"
    if any(_matches(item.text, check) for item in indexed):
        return "RETRIEVAL_MISS"
    if any(_matches(text, check) for text in processed):
        return "INDEX_MISSING"
    if raw_checked and any(_matches(text, check) for text in raw):
        return "EXTRACTION_MISSING"
    return "CORRECT_LIMITATION" if check.limitation else "SOURCE_ABSENT"


def _quality(missing: list[dict[str, str]], answer: str) -> str:
    causes = {entry["cause"] for entry in missing}
    if not answer:
        return "UNSUPPORTED"
    if not missing:
        return "GOOD"
    if causes <= {"CORRECT_LIMITATION", "SOURCE_ABSENT", "EXTRACTION_MISSING", "INDEX_MISSING"}:
        return "CORRECTLY_LIMITED" if "CORRECT_LIMITATION" in causes else "USABLE_BUT_THIN"
    return "VAGUE" if len(missing) > 2 else "USABLE_BUT_THIN"


def _service() -> ChatService:
    return ChatService(
        retriever=LocalChromaRetriever(), generator=None,
        retrieval_lock=threading.Lock(), generation_lock=threading.Lock(), model_name="audit-no-provider",
    )


def run_audit() -> dict[str, object]:
    """Execute all scenarios using production retrieval and planner code read-only."""
    before = _snapshot()
    retriever = LocalChromaRetriever()
    service = ChatService(
        retriever=retriever, generator=None,
        retrieval_lock=threading.Lock(), generation_lock=threading.Lock(), model_name="audit-no-provider",
    )
    indexed = list(retriever.indexed_chunks())  # public provider contract
    integrity = index_integrity(indexed)
    processed = _processed_texts()
    raw, raw_checked = _raw_pdf_texts()
    questions: list[dict[str, object]] = []
    for spec in AUDIT_QUESTIONS:
        request = ChatRequest(question=spec.question)
        understanding = understand_question(spec.question)
        retrieved = service._retrieve_evidence(request, None, understanding)
        # This public ten-result probe differentiates an effective eight-result
        # cutoff from a genuine production-route retrieval miss. It does not
        # change the answer route or index.
        ranked_candidates = list(retriever.search(spec.question, k=10))
        evidence = [TrustedEvidence(f"S{index}", item.chunk_id, item.text, item.source_filename,
                                    item.page_start, item.page_end)
                    for index, item in enumerate(retrieved, start=1)]
        plan = service._build_evidence_plan(spec.question, evidence, None, understanding)
        selected = [item for item, _ in plan.roles.values()]
        answer = ""
        sections: list[dict[str, object]] = []
        citations: list[dict[str, object]] = []
        execution = "deterministic"
        try:
            response = service.chat(request, understanding=understanding)
            answer = response.answer
            sections = [{"type": section.type, "title": section.title,
                         "content": section.content, "items": section.items,
                         "citation_ids": section.citation_ids} for section in response.answer_sections]
            citations = [{"citation_id": citation.citation_id, "chunk_id": citation.chunk_id,
                          "source_filename": citation.source_filename, "page_start": citation.page_start,
                          "page_end": citation.page_end} for citation in response.citations]
        except ProviderUnavailableError:
            execution = "provider-required-path-blocked"
        selected_ids = {item.chunk_id for item in selected}
        retrieved_ids = {item.chunk_id for item in retrieved}
        citation_integrity = all(citation["chunk_id"] in retrieved_ids for citation in citations)
        missing = [{"fact": check.name, "cause": _classify(check, answer, selected, retrieved, ranked_candidates,
                                                             indexed, processed, raw, raw_checked)}
                   for check in spec.facts if not _matches(answer, check)]
        primary_cause = missing[0]["cause"] if missing else "CORRECT_LIMITATION"
        questions.append({
            "id": spec.identifier, "question": spec.question,
            "understanding": {"intent": understanding.intent, "power": understanding.power,
                              "clarification_required": understanding.clarification_required},
            "retrieval_queries": [spec.question, *service._coverage_queries(spec.question, None, understanding)],
            "retrieved": [{"rank": rank, **_safe_metadata(item)} for rank, item in enumerate(retrieved, start=1)],
            "ranked_candidates": [{"rank": rank, **_safe_metadata(item)}
                                  for rank, item in enumerate(ranked_candidates, start=1)],
            "selected_evidence_ids": sorted(selected_ids), "plan_category": plan.category,
            "plan_roles": sorted(plan.roles), "execution": execution, "answer": answer,
            "answer_sections": sections, "citations": citations, "citation_integrity": citation_integrity,
            "missing_facts": missing, "primary_cause": primary_cause,
            "quality": _quality(missing, answer),
        })
    after = _snapshot()
    if before != after:
        raise RuntimeError("Protected paths changed during a read-only audit")
    return {"format": "answer-coverage-audit-v1", "raw_pdf_text_checked": raw_checked,
            "collection_count": retriever.count(), "index_integrity": integrity, "questions": questions}


def _output_path(value: str | None) -> Path:
    if value is None:
        return Path(tempfile.gettempdir()) / "bis-answer-coverage-audit.json"
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    protected = [(ROOT / item).resolve() for item in PROTECTED_PATHS]
    if any(path.resolve().is_relative_to(item) for item in protected):
        raise ValueError("Audit output must be outside protected paths")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="JSON report destination (default: system temporary directory)")
    args = parser.parse_args()
    try:
        output = _output_path(args.output)
    except ValueError as error:
        parser.error(str(error))
    report = run_audit()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {output.name}: {len(AUDIT_QUESTIONS)} questions; collection={report['collection_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
