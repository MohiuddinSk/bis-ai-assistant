from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parents[2]
RAW_DIR = ROOT / "data" / "raw"


def main() -> None:
    registry = json.loads((PACKAGE_DIR / "source_registry.json").read_text(encoding="utf-8"))
    duplicate_map = json.loads((PACKAGE_DIR / "duplicate_map.json").read_text(encoding="utf-8"))
    pages = [json.loads(line) for line in (PACKAGE_DIR / "pages.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    chunks = [json.loads(line) for line in (PACKAGE_DIR / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    raw_files = sorted(path.name for path in RAW_DIR.glob("*.pdf"))
    registered = sorted(source["source_filename"] for source in registry)
    if registered != raw_files:
        raise SystemExit(f"Registry mismatch: raw={raw_files}, registry={registered}")
    page_keys = {(page["source_filename"], page["page_number"]) for page in pages}
    for source in registry:
        expected = {(source["source_filename"], number) for number in range(1, source["page_count"] + 1)}
        if not expected.issubset(page_keys):
            raise SystemExit(f"Missing page record for {source['source_filename']}")
    ids = [row["id"] for row in chunks]
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate chunk IDs exist")
    documents = [row["document"] for row in chunks]
    if len(documents) != len(set(documents)):
        raise SystemExit("Exact duplicate chunks exist")
    allowed = (str, int, float, bool)
    for row in chunks:
        metadata = row.get("metadata", {})
        if not row.get("document", "").strip():
            raise SystemExit(f"Empty chunk: {row.get('id')}")
        for key in ("source_filename", "source_status", "page_start", "page_end", "char_count", "text_sha256"):
            if key not in metadata or metadata[key] in ("", None):
                raise SystemExit(f"Missing {key}: {row.get('id')}")
        if any(not isinstance(value, allowed) for value in metadata.values()):
            raise SystemExit(f"Non-Chroma-compatible metadata: {row.get('id')}")
        if metadata["char_count"] != len(row["document"]):
            raise SystemExit(f"char_count mismatch: {row.get('id')}")
    counts = Counter(row["metadata"]["source_filename"] for row in chunks)
    for source in registry:
        source_pages = [page for page in pages if page["source_filename"] == source["source_filename"]]
        if any(page["extraction_quality"] != "empty" for page in source_pages) and counts[source["source_filename"]] == 0:
            raise SystemExit(f"Non-empty source has no chunks: {source['source_filename']}")
    qualities = Counter(page["extraction_quality"] for page in pages)
    kinds = Counter(row["metadata"]["chunk_type"] for row in chunks)
    lengths = [len(row["document"]) for row in chunks]
    print(f"PDFs processed: {len(registry)}")
    print(f"Total PDF pages: {len(pages)}")
    print(f"Empty pages: {qualities['empty']}")
    print(f"Low-quality pages: {qualities['low']}")
    print(f"Canonical sources: {len(registry) - len(duplicate_map)}")
    print(f"Duplicate sources: {len(duplicate_map)}")
    print(f"Total chunks: {len(chunks)}")
    print(f"Document chunks: {kinds['document_text']}")
    print(f"Structured chunks: {kinds['structured_fact']}")
    print(f"Retrieval-enabled chunks: {sum(row['metadata'].get('retrieval_enabled') is True for row in chunks)}")
    print(f"Default retrieval chunks: {sum(row['metadata'].get('default_retrieval') is True for row in chunks)}")
    print("Chunks per PDF:")
    for filename in raw_files:
        print(f"  {filename}: {counts[filename]}")
    print(f"Minimum chunk length: {min(lengths)}")
    print(f"Maximum chunk length: {max(lengths)}")
    print(f"Average chunk length: {sum(lengths) / len(lengths):.2f}")


if __name__ == "__main__":
    main()
