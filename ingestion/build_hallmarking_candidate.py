"""Verify curated BIS excerpts and build an isolated Hallmarking evidence package.

This does not alter the V3/V4 PDF corpora or either Chroma collection. HTML
excerpts are checked against the current official page, while the PDF excerpt
is checked against the already reviewed V4 page extraction.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ingestion" / "hallmarking_sources.json"
V4_PAGES = ROOT / "data" / "processed" / "generated_v4" / "pages_complete.jsonl"
OUTPUT = ROOT / "data" / "processed" / "hallmarking_candidate_v1" / "evidence.json"


class VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ignored = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self.ignored = max(0, self.ignored - 1)

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def official_page(url: str) -> tuple[str, str]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "www.bis.gov.in":
        raise ValueError(f"Non-official source rejected: {url}")
    request = Request(url, headers={"User-Agent": "BIS-Bandhu-source-review/1.0"})
    with urlopen(request, timeout=25) as response:
        if response.status != 200 or response.url.split("/")[2] != "www.bis.gov.in":
            raise ValueError(f"Official source unavailable: {url}")
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError(f"Official page is unexpectedly large: {url}")
    parser = VisibleText()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return normalized(" ".join(parser.parts)), hashlib.sha256(raw).hexdigest()


def pdf_page_text(filename: str, page: int) -> str:
    for line in V4_PAGES.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("source_filename") == filename and row.get("page_number") == page:
            return normalized(row["text"])
    raise ValueError(f"Reviewed V4 PDF page not found: {filename} page {page}")


def build(output: Path = OUTPUT) -> dict[str, object]:
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or not entries:
        raise ValueError("Empty Hallmarking source manifest")
    seen_ids: set[str] = set()
    pages: dict[str, tuple[str, str]] = {}
    records: list[dict[str, object]] = []
    for entry in entries:
        if entry["id"] in seen_ids:
            raise ValueError(f"Duplicate source ID: {entry['id']}")
        seen_ids.add(entry["id"])
        if entry["source_type"] == "html":
            url = entry["source_url"]
            if url not in pages:
                pages[url] = official_page(url)
            text, source_hash = pages[url]
            if entry.get("source_filename") or entry.get("page"):
                raise ValueError("HTML evidence must not carry PDF filename/page metadata")
        elif entry["source_type"] == "pdf":
            filename, page = entry["source_filename"], entry["page"]
            text = pdf_page_text(filename, page)
            pdf = ROOT / "data" / "raw" / "jewellery" / filename
            if not pdf.is_file():
                raise ValueError(f"Reviewed PDF missing: {filename}")
            source_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
        else:
            raise ValueError("Unsupported source type")
        if normalized(entry["quote"]) not in text:
            raise ValueError(f"Excerpt not found in official source: {entry['id']}")
        if not entry["source_title"] or not entry["section_heading"] or not entry["summary"]:
            raise ValueError(f"Missing reviewed provenance: {entry['id']}")
        records.append({**entry, "source_sha256": source_hash})
    package: dict[str, object] = {
        "version": "hallmarking_candidate_v1",
        "retrieved_at": datetime.now(timezone.utc).date().isoformat(),
        "record_count": len(records),
        "records": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return package


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = build(args.output)
    print(f"Verified {result['record_count']} Hallmarking evidence excerpts into {args.output}")
