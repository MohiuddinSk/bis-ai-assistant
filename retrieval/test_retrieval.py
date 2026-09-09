from __future__ import annotations

import sys
from pathlib import Path

import chromadb

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
CHROMA_DIR = ROOT / "data" / "chroma"
QUESTIONS = [
    "Which standard applies to a non-electric plastic rattle?",
    "Which standard applies to a battery-operated toy?",
    "Can acoustic testing be subcontracted?",
    "What was the QCO commencement date?",
    "What documents are required for a new toy series?",
    "Can I import R&D toy samples?",
    "Are all handmade toys exempt?",
    "What does the 2026 transition order do?",
    "What is the latest product manual available?",
    "What information is needed before identifying applicable standards?",
]


def main() -> None:
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection(name="bis_toys_v2")
    print(f"COLLECTION_COUNT: {collection.count()}")
    for question in QUESTIONS:
        results = collection.query(query_texts=[f"query: {question}"], n_results=5)
        print(f"QUESTION: {question}")
        ids = results.get("ids", [[]])[0]
        if not ids:
            print("NO_RESULTS")
            print("------")
            continue
        for index, item_id in enumerate(ids):
            metadata = results["metadatas"][0][index]
            print({
                "result_id": item_id,
                "distance": results["distances"][0][index],
                "source_filename": metadata.get("source_filename", ""),
                "source_status": metadata.get("source_status", ""),
                "page_range": f"{metadata.get('page_start', '')}-{metadata.get('page_end', '')}",
                "chunk_type": metadata.get("chunk_type", ""),
                "preview": results["documents"][0][index][:500],
            })
        print("------")


if __name__ == "__main__":
    main()
