# Active v3 dataset

Generated from the eight PDFs in `data/raw` using `ingestion/extract_and_chunk.py`.
Run `python ingestion/validate_data.py` from the repository root before indexing.
See `docs/DATA_WORKFLOW.md` for Windows commands and quality limitations.

Use only this package with the collection in `embedding_manifest.json`. Chunk metadata is embedded in each JSONL record; no separate metadata file is needed. Page records preserve all page references, including repeated text and blank forms.

`retrieval_enabled` controls indexing; `default_retrieval` additionally excludes FAQ/procedural guidance. Source authenticity and legal currency are not verified. No hardcoded v2 fact summaries are included.
