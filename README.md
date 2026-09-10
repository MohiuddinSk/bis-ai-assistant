# BIS Toys RAG data pipeline

The active dataset is `data/processed/generated_v3`. Read [the operating guide](docs/DATA_WORKFLOW.md) before building the index.

The packages in `data/processed/`, `generated/`, and `generated_v2/` are retained as historical outputs. Their older hardcoded facts and retrieval scripts are superseded by v3. Do not combine these packages in a single collection.

No backend, LLM answer generation, or frontend is implemented by this data repair.

<details><summary>Previous team notes (historical commands; use the guide above)</summary>

# BIS AI Assistant

SIH PS26107: a document-grounded assistant for Indian Standards and BIS services.

This repository currently contains the document-ingestion and retrieval-preparation phase. The frontend, authentication, deployment, and LLM answer-generation layers are not part of this phase.

## Current Phase

The pipeline reads the eight PDFs in `data/raw/`, extracts every page, creates page-aware chunks, validates the generated package, embeds retrieval-enabled chunks into a local ChromaDB collection, and runs retrieval smoke tests.

The raw PDFs are inputs only and must not be edited. Previous generated outputs under `data/processed/generated/` are preserved. The current reproducible package is written to `data/processed/generated_v2/`.

## Verified Output

The current package was rebuilt and validated on 2026-09-09:

- PDFs processed: 8
- PDF pages processed: 89
- Empty pages: 0
- Low-quality pages: 2
- Unique chunks: 174
- Document chunks: 169
- Structured fact chunks: 5
- Retrieval-enabled chunks: 174
- Product manual chunks: 108
- Chroma chunks inserted in this phase: 174
- Existing `bis_toys_v2` collection count after upsert: 202
- Retrieval questions tested: 10

The two low-quality pages are pages 57 and 61 of `product_manual_2026.pdf`. They are retained in `pages.jsonl`; no page is silently discarded.

## Repository Layout

- `data/raw/`: source PDFs; do not modify
- `data/processed/generated_v2/`: current generated pages, chunks, registry, duplicate map, summary, and validator
- `data/processed/generated/`: previous generated package; preserved for comparison
- `data/chroma/`: local persistent ChromaDB; ignored by Git
- `ingestion/extract_and_chunk.py`: extraction, fallback extraction, cleaning, duplicate detection, chunking, and structured facts
- `ingestion/build_chroma.py`: E5 embeddings and ChromaDB upsert
- `retrieval/test_retrieval.py`: ten-question top-5 retrieval smoke test
- `backend/`, `frontend/`, `evaluation/`, and `docs/`: reserved for later phases

## Setup on Windows

Use the existing virtual environment if it is present:

```powershell
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

For a new environment:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Pinned compatibility requirements include `chromadb==0.4.24` and `numpy<2`. These avoid the Windows/NumPy compatibility problems encountered with newer combinations.

## Rebuild the Generated Package

Run from the repository root:

```powershell
python ingestion/extract_and_chunk.py
```

This always writes to `data/processed/generated_v2/` and does not overwrite the earlier generated package. Extraction uses `pypdf` first and retries a page with PyMuPDF when fewer than 50 meaningful characters are extracted.

Generated files:

- `pages.jsonl`: one record for every PDF page, including raw and cleaned text
- `source_registry.json`: one source record per PDF
- `duplicate_map.json`: exact-file, normalized-text, and near-duplicate checks
- `chunks.jsonl`: page-aware document and structured fact chunks
- `summary.json`: package totals
- `validate_chunks.py`: quality gate

## Required Validation Sequence

Always validate before embedding:

```powershell
python data/processed/generated_v2/validate_chunks.py
python ingestion/build_chroma.py
python retrieval/test_retrieval.py
```

Validation checks page coverage, source coverage, unique IDs, exact duplicate chunks, required metadata, Chroma-compatible metadata types, character counts, and source chunk counts.

The Chroma builder:

- uses `intfloat/multilingual-e5-small`
- stores cosine-distance embeddings
- uses batch size 128
- indexes every chunk where `retrieval_enabled` is `true`
- upserts into collection `bis_toys_v2`
- does not delete existing Chroma data automatically

The retrieval test uses `query: ` prefixes, UTF-8 output, top-5 results, and prints result ID, distance, source filename, source status, page range, chunk type, and a 500-character preview.

## Collaboration Rules

1. Do not edit files under `data/raw/`.
2. Do not delete `data/chroma/` automatically.
3. Do not overwrite `data/processed/generated/`; it is the previous package.
4. Rebuild `generated_v2` before changing retrieval or embedding behavior.
5. Run validation before Chroma ingestion.
6. Treat retrieval hits as evidence candidates, not proof that a legal rule is current.
7. Review low-quality pages and irrelevant top results manually.
8. Do not add virtual environments, model caches, or Chroma persistence files to Git.

## Next Phase Work

The ingestion and retrieval-preparation phase is complete. Suitable follow-up work includes:

- manual review or improved extraction for the two low-quality product-manual pages
- relevance evaluation for the ten retrieval questions
- citation formatting and answer-evidence contracts
- backend API integration
- LLM answer generation with legal-status and source-review safeguards
- frontend, authentication, and deployment

No LLM answer generation or user-facing chatbot behavior should be inferred from this phase alone.

</details>
