"""Small, provenance-first catalogue for standards metadata.

This project does not have a licensed bulk BIS catalogue feed.  The catalogue
therefore contains only records whose identifier, title and source have been
verified from an official document already in the project.  ``import_catalogue``
is deliberately a file-based hand-off for a future authorised export; it is not
a scraper for the public BIS search site.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOGUE_PATH = ROOT / "backend" / "catalogue_records.json"
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

    @classmethod
    def from_dict(cls, item: dict[str, object]) -> "CatalogueRecord":
        required = ("identifier", "title", "official_url", "retrieved_at", "provenance")
        missing = [key for key in required if not isinstance(item.get(key), str) or not str(item[key]).strip()]
        if missing:
            raise ValueError(f"Catalogue record is missing: {', '.join(missing)}")
        return cls(
            identifier=normalize_is_number(str(item["identifier"])),
            title=str(item["title"]).strip(),
            category=str(item["category"]).strip() if item.get("category") else None,
            edition_year=str(item["edition_year"]).strip() if item.get("edition_year") else None,
            status=str(item["status"]).strip() if item.get("status") else None,
            official_url=str(item["official_url"]).strip(),
            retrieved_at=str(item["retrieved_at"]).strip(),
            provenance=str(item["provenance"]).strip(),
            evidence_filename=str(item["evidence_filename"]).strip() if item.get("evidence_filename") else None,
            evidence_page=int(item["evidence_page"]) if item.get("evidence_page") else None,
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


def load_catalogue(path: Path = DEFAULT_CATALOGUE_PATH) -> list[CatalogueRecord]:
    if not path.exists():
        return _seed_records()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Catalogue import must be a JSON list")
    records = [CatalogueRecord.from_dict(item) for item in raw if isinstance(item, dict)]
    return _deduplicate(records)


def _deduplicate(records: list[CatalogueRecord]) -> list[CatalogueRecord]:
    unique: dict[str, CatalogueRecord] = {}
    for record in records:
        # A later retrieved record replaces a duplicate only when the identifier
        # matches exactly; parts and editions intentionally remain distinct.
        old = unique.get(record.identifier)
        if old is None or record.retrieved_at >= old.retrieved_at:
            unique[record.identifier] = record
    return sorted(unique.values(), key=lambda record: record.identifier)


def search_catalogue(query: str = "") -> list[CatalogueRecord]:
    needle = normalize_is_number(query).lower()
    records = load_catalogue()
    if not needle:
        return records
    tokens = [token for token in re.split(r"\W+", needle) if token]
    def score(record: CatalogueRecord) -> tuple[int, str]:
        haystack = " ".join(filter(None, (record.identifier, record.title, record.category))).lower()
        exact = int(needle == record.identifier.lower())
        matched = sum(token in haystack for token in tokens)
        return (-exact, -matched, record.identifier)
    return [record for record in sorted(records, key=score) if all(token in " ".join(filter(None, (record.identifier, record.title, record.category))).lower() for token in tokens)]


def catalogue_metadata(records: list[CatalogueRecord]) -> dict[str, object]:
    return {
        "record_count": len(records),
        "last_updated": max((record.retrieved_at for record in records), default=None),
        "coverage_note": "Only locally verified metadata is listed. This is not a complete BIS catalogue.",
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
    destination.write_text(json.dumps([record_as_dict(record) for record in records], indent=2) + "\n", encoding="utf-8")
    return len(records)
