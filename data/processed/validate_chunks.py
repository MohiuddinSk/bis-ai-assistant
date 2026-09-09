import json
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
CHUNKS_FILE = PACKAGE_DIR / "chunks.jsonl"

rows = [
    json.loads(line)
    for line in CHUNKS_FILE.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

assert rows, "No chunks found in chunks.jsonl"
assert len({row["id"] for row in rows}) == len(rows), "Duplicate chunk IDs found"

allowed_types = (str, int, float, bool)

for row in rows:
    assert isinstance(row["id"], str)
    assert isinstance(row["document"], str)
    assert row["document"].strip(), f"Empty document: {row['id']}"
    assert all(
        isinstance(value, allowed_types)
        for value in row["metadata"].values()
    ), f"Non-Chroma-compatible metadata: {row['id']}"
    assert row["metadata"]["char_count"] == len(row["document"])
    assert row["metadata"]["text_sha256"]

print({
    "chunks": len(rows),
    "ids_unique": True,
    "metadata_chroma_compatible": True,
    "min_chars": min(len(row["document"]) for row in rows),
    "max_chars": max(len(row["document"]) for row in rows),
})
