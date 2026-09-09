from __future__ import annotations

import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
CHUNKS_FILE = ROOT / "data" / "processed" / "generated_v2" / "chunks.jsonl"
CHROMA_DIR = ROOT / "data" / "chroma"
COLLECTION_NAME = "bis_toys_v2"


def main() -> None:
    rows = [json.loads(line) for line in CHUNKS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    chunks = [row for row in rows if row["metadata"].get("retrieval_enabled") is True]
    print("Embedding model: intfloat/multilingual-e5-small")
    model = SentenceTransformer("intfloat/multilingual-e5-small")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    for start in range(0, len(chunks), 128):
        batch = chunks[start:start + 128]
        embeddings = model.encode([row["document"] for row in batch], normalize_embeddings=True, convert_to_numpy=True).tolist()
        collection.upsert(ids=[row["id"] for row in batch], documents=[row["document"] for row in batch], metadatas=[row["metadata"] for row in batch], embeddings=embeddings)
    print(f"Chunks selected: {len(chunks)}")
    print(f"Chunks inserted: {len(chunks)}")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Chroma path: {CHROMA_DIR}")
    print(f"Final collection count: {collection.count()}")


if __name__ == "__main__":
    main()
