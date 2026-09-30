"""Source-backed standards metadata, separate from document-grounded answers."""

from __future__ import annotations

import gzip
import json
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOGUE_PATH = ROOT / "backend" / "catalogue_records.json"
EXPANDED_CATALOGUE_PATH = ROOT / "data" / "reference" / "bis_directories" / "standards.json.gz"
_IS_NUMBER = re.compile(r"^IS\s+(\d{1,6})(?:\s+Part\s+(\d{1,2}))?(?::\s*(\d{4}))?$", re.I)


def normalize_is_number(value: str) -> str:
    """Return a stable display form without guessing a missing edition."""
    cleaned = re.sub(r"\s+", " ", value.strip().upper().replace("-", " "))
    match = _IS_NUMBER.fullmatch(cleaned)
    if not match:
        return cleaned
    number, part, year = match.groups()
    result = f"IS {number}"
    if part:
        result += f" Part {part}"
    if year:
        result += f":{year}"
    return result


def standard_identity(value: str) -> str:
    """Compare IS spellings without collapsing parts, sections, or editions."""
    normalized = re.sub(r"[^A-Z0-9]", "", value.upper())
    return "IS" + normalized if normalized and normalized[0].isdigit() else normalized


@dataclass(frozen=True)
class CatalogueRecord:
    identifier: str
    title: str
    category: str | None
    edition_year: str | None
    status: str | None
    official_url: str
    retrieved_at: str
    provenance: str
    evidence_filename: str | None = None
    evidence_page: int | None = None
    part: str | None = None
    section: str | None = None
    source_publication_date: str | None = None
    official_detail_url: str | None = None
    source_row: int | None = None

    @classmethod
    def from_dict(cls, item: dict[str, object]) -> "CatalogueRecord":
        required = ("identifier", "title", "official_url", "retrieved_at", "provenance")
        missing = [key for key in required if not isinstance(item.get(key), str) or not str(item[key]).strip()]
        if missing:
            raise ValueError(f"Catalogue record is missing: {', '.join(missing)}")
        return cls(
            identifier=str(item["identifier"]).strip() if item.get("source_row") else normalize_is_number(str(item["identifier"])),
            title=str(item["title"]).strip(),
            category=str(item["category"]).strip() if item.get("category") else None,
            edition_year=str(item["edition_year"]).strip() if item.get("edition_year") else None,
            status=str(item["status"]).strip() if item.get("status") else None,
            official_url=str(item["official_url"]).strip(),
            retrieved_at=str(item["retrieved_at"]).strip(),
            provenance=str(item["provenance"]).strip(),
            evidence_filename=str(item["evidence_filename"]).strip() if item.get("evidence_filename") else None,
            evidence_page=int(item["evidence_page"]) if item.get("evidence_page") else None,
            part=str(item["part"]).strip() if item.get("part") else None,
            section=str(item["section"]).strip() if item.get("section") else None,
            source_publication_date=str(item["source_publication_date"]).strip() if item.get("source_publication_date") else None,
            official_detail_url=str(item["official_detail_url"]).strip() if item.get("official_detail_url") else None,
            source_row=int(item["source_row"]) if item.get("source_row") else None,
        )


def _seed_records() -> list[CatalogueRecord]:
    # Verified verbatim from PM_IS_4151_-Dec-24.pdf, page 1, kept as metadata
    # rather than a copy of the standard's protected technical text.
    return [CatalogueRecord(
        identifier="IS 4151:2015",
        title="Protective Helmet for Two Wheeler Riders",
        category="Helmet",
        edition_year="2015",
        status="Title and identifier verified from the cited BIS product manual",
        official_url="https://www.bis.gov.in/wp-content/uploads/2024/12/PM_IS_4151_-Dec-24.pdf",
        retrieved_at="2024-12",
        provenance="BIS Product Manual PM/IS 4151/3/Dec 2024, page 1",
        evidence_filename="PM_IS_4151_-Dec-24.pdf",
        evidence_page=1,
    )]


@lru_cache(maxsize=4)
def _load_cached(base: str, base_mtime: int, expanded: str, expanded_mtime: int) -> tuple[CatalogueRecord, ...]:
    del base_mtime, expanded_mtime  # cache keys make refreshed snapshots visible
    path = Path(base)
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else [asdict(record) for record in _seed_records()]
    if not isinstance(raw, list):
        raise ValueError("Catalogue import must be a JSON list")
    records = [CatalogueRecord.from_dict(item) for item in raw]
    expanded_path = Path(expanded)
    if expanded_path.exists():
        imported = json.loads(gzip.decompress(expanded_path.read_bytes()))
        if not isinstance(imported, list):
            raise ValueError("Expanded catalogue must be a JSON list")
        records.extend(CatalogueRecord.from_dict(item) for item in imported)
    return tuple(_deduplicate(records))


def load_catalogue(path: Path = DEFAULT_CATALOGUE_PATH, expanded_path: Path = EXPANDED_CATALOGUE_PATH) -> list[CatalogueRecord]:
    return list(_load_cached(str(path), path.stat().st_mtime_ns if path.exists() else 0,
                             str(expanded_path), expanded_path.stat().st_mtime_ns if expanded_path.exists() else 0))


def _deduplicate(records: list[CatalogueRecord]) -> list[CatalogueRecord]:
    unique: dict[str, CatalogueRecord] = {}
    for record in records:
        key = standard_identity(record.identifier)
        old = unique.get(key)
        # Existing independently checked records carry stronger direct-source
        # provenance than the broad Excel listing and must not be overwritten.
        if old is None or (not old.evidence_filename and not old.official_url.startswith("https://www.bis.gov.in/")
                           and record.retrieved_at > old.retrieved_at):
            unique[key] = record
    return sorted(unique.values(), key=lambda record: (record.identifier != "IS 4151:2015", record.source_row or 999999, record.identifier))


def search_catalogue(query: str = "", category: str = "", records: list[CatalogueRecord] | None = None) -> list[CatalogueRecord]:
    needle = query.strip().casefold()
    records = records if records is not None else load_catalogue()
    if category:
        records = [record for record in records if (record.category or "").casefold() == category.casefold()]
    if not needle:
        return records
    identity = standard_identity(query)
    tokens = [token for token in re.split(r"[^\w]+", needle) if token and token != "is"]
    def matches(record: CatalogueRecord) -> bool:
        haystack = " ".join(filter(None, (record.identifier, record.title, record.category))).casefold()
        if identity and identity == standard_identity(record.identifier):
            return True
        if re.search(r"\d", needle) and standard_identity(record.identifier).startswith(identity):
            return True
        return bool(tokens) and all(token in haystack for token in tokens)
    def score(record: CatalogueRecord) -> tuple[int, int, str]:
        record_id = standard_identity(record.identifier)
        title = record.title.casefold()
        rank = 0 if identity == record_id else 1 if record_id.startswith(identity) else 2 if needle in title else 3
        return (rank, record.source_row or 999999, record.identifier)
    return sorted((record for record in records if matches(record)), key=score)


def catalogue_metadata(records: list[CatalogueRecord]) -> dict[str, object]:
    return {
        "record_count": len(records),
        "last_updated": max((record.retrieved_at for record in records), default=None),
        "coverage_note": "Official BIS published-standard metadata is indexed. Titles do not provide technical requirements or establish applicability; check the official record.",
    }


def record_as_dict(record: CatalogueRecord) -> dict[str, object]:
    return asdict(record)


def import_catalogue(source: Path, destination: Path = DEFAULT_CATALOGUE_PATH) -> int:
    """Validate and atomically write an authorised metadata JSON export.

    Operators must supply the licensed/authorised export themselves.  This
    avoids a brittle or unauthorised scrape of BIS's public search interface.
    """
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Catalogue import must be a JSON list")
    records = _deduplicate([CatalogueRecord.from_dict(item) for item in raw if isinstance(item, dict)])
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps([record_as_dict(record) for record in records], indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return len(records)
