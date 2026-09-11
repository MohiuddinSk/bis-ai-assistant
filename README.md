# BIS Toys RAG data pipeline

This repository contains the document-ingestion and retrieval-preparation pipeline for the BIS Toys assistant. Backend, LLM answer generation, frontend, authentication, and deployment are outside its scope.

The active data package is `data/processed/generated_v3`. Previous packages under `data/processed/generated/` and `data/processed/generated_v2/` are historical outputs only; do not combine them with v3 in one collection.

## Verified Windows setup and pipeline

Use Python 3.11 and the `venv311` virtual environment. Run these commands from the repository root in Windows PowerShell, in order:

```powershell
py -3.11 -m venv venv311
.\venv311\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONUTF8 = "1"
.\venv311\Scripts\python.exe ingestion\extract_and_chunk.py
.\venv311\Scripts\python.exe ingestion\validate_data.py
.\venv311\Scripts\python.exe -m unittest discover -s tests -v
.\venv311\Scripts\python.exe ingestion\build_chroma.py
.\venv311\Scripts\python.exe retrieval\test_retrieval.py
```

Each command must complete successfully before continuing. The repair branch has already been merged into `main`; use the default branch and do not use a separate repair branch.

Pinned runtime dependencies are `chromadb==0.5.23`, `sentence-transformers==3.4.1`, `transformers==4.46.3`, `torch==2.5.1`, `tokenizers==0.20.3`, and `numpy==1.26.4`.

## What the pipeline does

The pipeline reads the eight PDFs in `data/raw/`, extracts and chunks their content, validates `data/processed/generated_v3`, builds a local ChromaDB index, and runs retrieval smoke tests. The raw PDFs are immutable inputs.

- `data/processed/generated_v3/`: active pages, chunks, source registry, duplicate map, manifests, summaries, and validator outputs
- `ingestion/extract_and_chunk.py`: extraction, cleaning, duplicate detection, chunking, and structured facts
- `ingestion/validate_data.py`: generated-data validation
- `ingestion/build_chroma.py`: embeddings and ChromaDB index build
- `retrieval/test_retrieval.py`: retrieval smoke test
- `data/chroma/`: local ChromaDB persistence

`data/chroma/` is local state and must not be committed. Each developer rebuilds their own index with the verified workflow. Likewise, do not commit virtual environments, credentials, or model caches.

JSONL files are versioned with LF line endings: `.gitattributes` enforces `*.jsonl text eol=lf`. Keep generated JSONL files in that format.

## Data and retrieval safeguards

Validate the generated package before building Chroma. Do not manually copy chunks from an older package into the v3 collection, and do not delete local Chroma data automatically.

Retrieval results are evidence candidates, not proof that a legal rule is current or complete. Check the cited source, page context, applicable amendments, and conditions before relying on a result.

For fuller operational detail, see [docs/DATA_WORKFLOW.md](docs/DATA_WORKFLOW.md).
