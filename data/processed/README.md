# BIS Toys RAG Chunk Package

This package is ready for embedding and insertion into ChromaDB or another vector database. It contains source-aware document chunks and structured fact chunks. It does not contain embeddings. Generate embeddings with the model selected by the team.

## Recommended Chroma import

```python
import json, chromadb
from sentence_transformers import SentenceTransformer
records=[json.loads(line) for line in open("chunks.jsonl", encoding="utf-8")]
# Start with default_retrieval=True; include historical records only for comparison queries.
model=SentenceTransformer("BAAI/bge-m3")  # select and pin the team model
client=chromadb.PersistentClient(path="./chroma")
collection=client.get_or_create_collection("bis_toys_v1", metadata={"hnsw:space":"cosine"})
for i in range(0,len(records),256):
    batch=records[i:i+256]
    collection.upsert(ids=[x["id"] for x in batch],documents=[x["document"] for x in batch],metadatas=[x["metadata"] for x in batch],embeddings=model.encode([x["document"] for x in batch],normalize_embeddings=True).tolist())
```

Use `chroma_documents.json` if you want one import object containing parallel `ids`, `documents` and `metadatas`. Use `chunks.jsonl` for streaming. Every metadata value is a string, integer, float or boolean, which is compatible with Chroma metadata constraints.

## Retrieval policy

Filter `default_retrieval == true` for ordinary current-oriented answers. Historical and unverified guidance remains available for conflict/version comparison but should not win ordinary retrieval. Every result has `source_id`, URL, section, printed page when known, source status, chunk type and review status. `printed_page == -1` means the supplied extraction did not establish a reliable page.

Document chunks retain source text and are marked `raw_extraction_needs_layout_review`. Structured fact chunks are shorter and safer for rules, standards, taxonomy, forms and testing records. Duplicate PDF copies are excluded from the canonical document corpus and recorded in `duplicate_map.json`.

The source data has mixed Hindi/English extraction, repeated headers, tables and older manual revisions. Do not train or answer from all chunks indiscriminately. Apply metadata filters, rerank by source status/version and preserve citations in the RAG response.
