# BIS Toys RAG data pipeline

This repository contains the document-ingestion and retrieval-preparation pipeline for the BIS Toys assistant, a retrieval API, and a grounded chat endpoint backed by Groq. Frontend, authentication, and deployment are outside this phase.

The active data package is `data/processed/generated_v3`. Previous packages under `data/processed/generated/` and `data/processed/generated_v2/` are historical outputs only; do not combine them with v3 in one collection.

## Frontend MVP

The React/Vite frontend lives in `frontend/` and communicates only with the local API; it never contains provider credentials.

```powershell
cd frontend
npm install
npm run dev
```

Leave `VITE_API_BASE_URL` empty to use the Vite proxy to `http://127.0.0.1:8000`. Verify with `npm run lint`, `npm run test -- --run`, and `npm run build`.

Source citations open only registered PDFs through `GET /api/documents/{source_filename}`; use the citation link rather than a local file path.

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

## Retrieval API

The FastAPI service exposes the existing local Retriever without changing its embeddings, ranking, collection, or evidence text. Python 3.11 and a populated local Chroma collection are required.

Install the pinned dependencies and build Chroma if the manifest collection has not already been built:

```powershell
.\venv311\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONUTF8 = "1"
.\venv311\Scripts\python.exe ingestion\validate_data.py
.\venv311\Scripts\python.exe ingestion\build_chroma.py
```

Start the API from the repository root:

```powershell
$env:PYTHONUTF8 = "1"
.\venv311\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Available endpoints:

- `GET /health` reports whether the singleton Retriever loaded and returns the collection count; it does not run a search.
- `POST /api/retrieve` retrieves ranked evidence from the local v3 collection.
- `POST /api/chat` retrieves evidence and asks Groq for a structured, evidence-grounded answer with backend-verified citations.
- `GET /docs` opens the generated Swagger UI at `http://127.0.0.1:8000/docs`.

Example request:

```json
{
  "question": "Which standard applies to a battery-operated toy?",
  "top_k": 5,
  "include_guidance": false
}
```

Example response shape:

```json
{
  "question": "Which standard applies to a battery-operated toy?",
  "result_count": 1,
  "results": [
    {
      "rank": 1,
      "chunk_id": "retrieved-chunk-id",
      "text": "passage: Retrieved evidence text",
      "source_id": "source-id",
      "source_filename": "product_manual_2026.pdf",
      "page_start": 12,
      "page_end": 12,
      "chunk_type": "document_text",
      "distance": 0.18,
      "similarity": 0.82
    }
  ]
}
```

Chroma cosine distance is lower when passages are closer to the query. The API also returns `similarity = 1.0 - distance`; similarity is retrieval closeness, not legal certainty, factual confidence, or a probability that an answer is correct.

Retrieved passages are evidence candidates requiring appropriate human review. The retrieval endpoint does not provide final legal advice.

## Grounded Chat API

`POST /api/chat` uses the same singleton Retriever and local Chroma collection. It sends only the current question and retrieved evidence to Groq, using `openai/gpt-oss-120b` by default. No Groq web search, tools, or external knowledge lookup is enabled.

Set `GROQ_API_KEY` in the process environment before starting the server. Do not put a real key in source control. [.env.example](.env.example) documents the supported configuration:

```text
GROQ_API_KEY=
LLM_PROVIDER=groq
GROQ_MODEL=openai/gpt-oss-120b
LLM_TIMEOUT_SECONDS=30
LLM_MAX_OUTPUT_TOKENS=800
```

Start the server:

```powershell
$env:PYTHONUTF8 = "1"
.\venv311\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Example chat request:

```json
{
  "question": "Which standard applies to a battery-operated toy?",
  "top_k": 5,
  "include_guidance": false
}
```

Example response shape:

```json
{
  "answer": "Grounded answer based only on the retrieved evidence.",
  "grounded": true,
  "insufficient_evidence": false,
  "evidence_count": 5,
  "citations": [
    {
      "citation_id": "S1",
      "source_filename": "product_manual_2026.pdf",
      "page_start": 12,
      "page_end": 12,
      "chunk_id": "retrieved-chunk-id",
      "excerpt": "passage: Retrieved evidence text"
    }
  ],
  "model": "openai/gpt-oss-120b",
  "disclaimer": "Informational guidance based on the indexed BIS documents. Verify requirements with BIS or a qualified professional."
}
```

The model may cite only temporary trusted IDs such as `S1` and must pair each with a 20–500 character verbatim supporting quote. The backend validates the ID and quote against the trusted passage, then supplies the real filename, page range, and chunk ID. The displayed excerpt is that validated quote; model-authored citation metadata is rejected. Duplicate citation/quote pairs are removed without changing their order.

If retrieved evidence is empty, the validated model output says evidence is insufficient, or structured output remains invalid after one repair retry, the API returns a safe abstention instead of an unsupported conclusion. Missing or invalid Groq configuration returns HTTP 503, timeouts return HTTP 504, and rate limits return HTTP 503 with `Retry-After` when Groq supplies it.

Chat output is informational guidance based on indexed BIS documents. It is not final legal advice; verify requirements with BIS or a qualified professional.

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

## Manufacturer Compliance Wizard

Start the API with `./venv311/Scripts/python.exe -m uvicorn backend.main:app --reload`, then start the frontend with `npm run dev` from `frontend/`. Choose **Compliance Wizard** to build a product profile without needing BIS terminology. The wizard calls `POST /api/compliance/guide`; selections guide retrieval but never count as legal evidence. The existing free-form chat remains available.
