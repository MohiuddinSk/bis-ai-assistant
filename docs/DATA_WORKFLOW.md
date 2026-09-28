# Data workflow (v3)

`data/processed/generated_v3` is the active data package. The repair branch has already been merged into `main`; work from the repository root on the default branch and do not use a separate repair branch.

Raw PDFs are immutable inputs. Older generated packages and old Chroma collections are retained only for comparison and must not be mixed with v3.

## Windows PowerShell

Use Python 3.11 and the `venv311` virtual environment. Run the verified sequence from the repository root:

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

Each command must exit successfully before proceeding. Do not use Bash heredocs in PowerShell.

The pinned dependencies are `chromadb==0.5.23`, `sentence-transformers==3.4.1`, `transformers==4.46.3`, `torch==2.5.1`, `tokenizers==0.20.3`, and `numpy==1.26.4`.

## What gets generated

- `pages.jsonl`: every PDF page, selected raw extraction, cleaned text, extractor and errors, and chunk IDs
- `chunks.jsonl`: document excerpts and table rows with scalar Chroma metadata and tokenizer counts
- `source_registry.json`: source hashes, physical page counts, source type, and observed revision where supported by text
- `duplicate_map.json`: exact-file canonicalization, repeated text with retained page provenance, and near-document candidates for review
- `embedding_manifest.json`: model revision, prefixes, distance metric, chunk-file hash, and collection name
- `summary.json`: counts and pages needing review

## Corpus V4 staging (not production)

`data/processed/generated_v4` and `data/chroma_v4_staging` are an isolated,
opt-in corpus package and collection. They must never replace `generated_v3` or
`data/chroma`. Build only after the source-verification manifest approves the
input hashes:

```powershell
python ingestion\extract_v4.py
python ingestion\build_chroma_v4.py
python -m unittest discover -s tests -p "test_corpus_v4_contract.py" -v
```

V4 snapshot sources retain their live-verification metadata. A laboratory
snapshot cannot recommend a lab without checking live LIMS scope and validity;
fee snapshots require an as-of date and scheme. Roll back V4 by ceasing use of
the staging package/collection; never delete or alter V3 as part of rollback.

The builder validates its input, requires exact collection membership, and does not delete old collections. Repeating a build is idempotent. Do not manually copy chunks from older generated packages into the v3 collection.

### FMCS OCR and candidate index

The approved FMCS forms use deterministic offline OCR sidecars under
`generated_v4/fmcs_ocr`. The candidate persistence path is
`data/chroma_v4_candidate`; production `data/chroma` is refused by the builder.
Candidate collection names include the complete-artifact hash, so changed
artifacts cannot silently reuse stale membership. Candidate artifacts do not
activate V4 at runtime.

## Local Chroma and Git hygiene

`data/chroma/` is local ChromaDB persistence and must not be committed. Each teammate rebuilds their own index with `ingestion/build_chroma.py`. Also keep virtual environments, credentials, and model caches out of Git.

`.gitattributes` enforces LF line endings for JSONL files (`*.jsonl text eol=lf`). Preserve LF when generating or editing JSONL output.

## Read-only real-index acceptance

Use this local, manual acceptance harness only when the local Chroma index, the cached pinned E5 model, and a working Python 3.11 environment are already available:

```powershell
.\scripts\test_real_index.ps1
```

It is intentionally excluded from hosted PR CI. The harness uses the existing index and artifacts; it does not rebuild, ingest, regenerate, or modify data. It hashes protected raw, processed, evaluation, and local Chroma files before and after execution, and fails if any protected hash differs.

If Python is missing, repair the local Python 3.11 environment before running it. If the index is missing, build it through the documented local data workflow before attempting acceptance. If the offline E5 model cache is missing, populate the pinned model cache through the approved local setup before running this offline check.

## Source and retrieval policy

Hardcoded structured summaries from v2 are not part of active retrieval. Source excerpts retain conditions and actual page references. Table rows preserve left-to-right cells without guessing continuation headers; consult the PDF for merged cells, continuation tables, and ambiguous layouts. No text is deleted merely because it repeats across pages. Oversized passages split at whitespace and do not silently truncate inside the encoder.

Repository URLs locate audited files; they are not official-publication verification. `official_url` is empty when unknown, authority is unverified, and no source is asserted to be the latest legally effective version. `document_revision` and `publication_date` record observed text rather than filename assumptions. Blank section/clause fields mean no literal local label was found; labels are never invented.

Use `Retriever.page_context(hit_metadata)` to recover the cited page when conditions span chunks. Do not infer an exemption, current commencement date, or complete applicable standards list from one fragment; retrieve and inspect the applicable order and amendment chain.

## Retrieval quality gate

`evaluation/questions.json` contains ten evidence-location checks. `retrieval/test_retrieval.py` writes passages, distances, and timings to `evaluation/retrieval_results.json` and exits nonzero for a missing expected source or page. An evidence hit is not proof that every condition needed for an answer is present. Review each saved result for complete conditions, authoritative source, correct citation, and conflicting amendments.

The first query includes model startup time; later timings are warm. These checks are diagnostic, not a production performance benchmark. Do not loosen expected pages solely to make tests pass.

## V4 candidate pre-promotion gate

Use only `data/chroma_v4_candidate_01346f7d11f1` and `bis_corpus_v4_candidate_01346f7d11f1` for the reviewed candidate. It remains isolated from active `data/chroma`. Candidate response safety uses explicit Retriever overrides with synthesis disabled. Laboratory and fee snapshots require live official verification for current scope, recognition, or fee claims.
