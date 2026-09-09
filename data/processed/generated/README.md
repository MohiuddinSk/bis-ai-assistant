# Generated BIS Toys RAG Data

This folder contains the reproducible processed package used to prepare BIS toy documents for retrieval-augmented generation.

## Raw inputs processed

The pipeline reads every PDF from [data/raw](../../raw) and extracts text page by page using pypdf. The source file, file hash, page number, and page text are kept in the generated page-level extraction file.

## Duplicate handling

Every file is hashed using SHA-256. Files with identical content are checked as exact or same-text duplicates, and near-duplicate similarity is tracked in the duplicate map. Canonical sources are retained and duplicates are flagged rather than re-embedded.

## Chunk creation

The cleaned page text is segmented into chunks sized roughly 800-1200 characters with a 150-200 character overlap. Chunks preserve source metadata, page ranges, and source status, and they are stored as UTF-8 JSONL records.

## Current candidates and review sources

Current candidate documents include the product manual and official legal sources. Guidance and FAQ documents remain available for review but are not treated as the primary default retrieval set unless explicitly allowed by metadata.

## How to rebuild the chunks

```bash
python ingestion/extract_and_chunk.py
python data/processed/generated/validate_chunks.py
```

## How to build ChromaDB

```bash
python ingestion/build_chroma.py
```

## How to run retrieval tests

```bash
python retrieval/test_retrieval.py
```

## Notes

- The raw PDFs are preserved and never modified.
- The generated outputs live under this folder and are separate from the legacy processed package.
- Embedded retrieval is not treated as legal verification of current status.
