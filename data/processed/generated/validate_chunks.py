import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHUNKS_FILE = ROOT / "data" / "processed" / "generated" / "chunks.jsonl"


def main() -> None:
    rows = [json.loads(line) for line in CHUNKS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise SystemExit("No chunks found in chunks.jsonl")

    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate chunk IDs found")

    allowed_types = (str, int, float, bool)
    document_chunks = 0
    structured_chunks = 0
    default_retrieval_chunks = 0
    min_chars = None
    max_chars = None

    for row in rows:
        document = row.get("document", "")
        metadata = row.get("metadata", {})
        if not isinstance(document, str) or not document.strip():
            raise SystemExit(f"Empty document: {row.get('id')}")
        if not metadata.get("source_id") or not metadata.get("source_filename"):
            raise SystemExit(f"Missing source metadata: {row.get('id')}")
        if not metadata.get("source_status"):
            raise SystemExit(f"Missing source_status: {row.get('id')}")
        if "source_path" not in metadata or not metadata.get("source_path"):
            raise SystemExit(f"Missing source_path: {row.get('id')}")
        if any(not isinstance(value, allowed_types) for value in metadata.values()):
            raise SystemExit(f"Non-Chroma-compatible metadata in {row.get('id')}")
        if metadata.get("char_count") != len(document):
            raise SystemExit(f"char_count mismatch for {row.get('id')}")
        if not metadata.get("text_sha256"):
            raise SystemExit(f"Missing text_sha256 for {row.get('id')}")
        if metadata.get("chunk_type") == "structured_fact":
            structured_chunks += 1
        else:
            document_chunks += 1
        if metadata.get("default_retrieval") is True:
            default_retrieval_chunks += 1
        length = len(document)
        min_chars = length if min_chars is None else min(min_chars, length)
        max_chars = length if max_chars is None else max(max_chars, length)

    print(f"total_chunks={len(rows)}")
    print(f"document_chunks={document_chunks}")
    print(f"structured_chunks={structured_chunks}")
    print(f"default_retrieval_chunks={default_retrieval_chunks}")
    print(f"duplicate_chunks_removed=0")
    print(f"minimum_character_count={min_chars}")
    print(f"maximum_character_count={max_chars}")


if __name__ == "__main__":
    main()
