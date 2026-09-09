# BIS AI Assistant

SIH PS26107 — AI-powered assistant for Indian Standards and BIS Services.

## Repository structure

- `data/raw/` — original PDFs and source exports
- `data/processed/` — cleaned, deduplicated, citation-aware RAG chunks
- `data/chroma/` — local ChromaDB persistence; ignored by Git
- `ingestion/` — PDF cleaning and Chroma ingestion scripts
- `retrieval/` — vector, keyword and hybrid retrieval code
- `backend/` — API service
- `frontend/` — user interface
- `evaluation/` — questions, expected citations and test results
- `docs/` — architecture and team documentation

## First setup

```powershell
python -m venv .venv
.\\.venv\\Scripts\\activate
pip install -r requirements.txt
python data/processed/validate_chunks.py
```

The processed package currently contains 530 unique chunks. Embeddings are not included; generate them only after the team selects and records the embedding model.
