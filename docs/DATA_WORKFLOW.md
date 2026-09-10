# Data workflow (v3)

Use Python 3.12 in a virtual environment. Work from the repository root on the repair branch until it is merged. Raw PDFs are immutable inputs; generated v3 is the only active package. Old packages and Chroma collections are preserved for comparison.

## Windows PowerShell

```powershell
git fetch origin
git switch fix/rag-data-integrity
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONUTF8 = "1"
.\venv\Scripts\python.exe ingestion/extract_and_chunk.py
.\venv\Scripts\python.exe ingestion/validate_data.py
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe ingestion/build_chroma.py
.\venv\Scripts\python.exe retrieval/test_retrieval.py
```

Each command must exit successfully before proceeding. Do not use Bash heredocs in PowerShell. On Linux/macOS use the virtual environment's Python with the same script paths. Linux building Chroma 0.4.24 from source may require a C++ compiler.

The first run downloads the pinned E5 model/tokenizer; later runs use the local model cache. Both indexing and retrieval explicitly use the same model revision, normalized vectors, and `passage: `/`query: ` prefixes. Reuse one `Retriever` instance per application process to avoid reloading the model and checking index membership on each request.

## What gets generated

- `pages.jsonl`: every PDF page, selected raw extraction, cleaned text, extractor and errors, and chunk IDs.
- `chunks.jsonl`: document excerpts and table rows with scalar Chroma metadata and exact tokenizer counts (480-token ceiling).
- `source_registry.json`: source hashes, physical page counts, source type, and observed revision where supported by text.
- `duplicate_map.json`: exact-file canonicalization, repeated text with retained page provenance, and near-document candidates retained for review.
- `embedding_manifest.json`: pinned model revision, prefixes, distance metric, chunk-file hash, and collection name.
- `summary.json`: counts and pages needing review.

Every new source inventory/pipeline version has a dataset ID. The collection name also includes the generated chunk-file hash. The builder validates input and requires exact collection membership; it never deletes old collections. Repeating a build is idempotent. Search refuses an incomplete or incompatible collection. Do not manually copy older chunks into it.

## Source and extraction policy

Hardcoded structured summaries from v2 have been removed from active retrieval. Source excerpts retain conditions and actual page references. Table rows preserve left-to-right cells without guessing continuation headers; consult the PDF for merged cells, continuation tables and ambiguous layouts. No text is deleted just because it repeats across pages. Oversized passages split at whitespace and never silently truncate inside the encoder.

Page 57 and 61 of the uploaded May 2026 manual were visually checked and are blank model/photo forms. Both retain their own page/chunk references. Other short pages are flagged and excluded until reviewed. FAQ/procedural guidance is available through `include_guidance=True`, but excluded from default retrieval. Unknown new files are extracted but not enabled until their source classification is added and reviewed.

Repository URLs locate the audited files; they are **not official publication verification**. `official_url` is empty when unknown, authority is unverified, and no source is asserted to be the latest legally effective version. `document_revision` and `publication_date` record observed text, not filename assumptions. Blank section/clause fields mean no literal local label was found; labels are never invented. Form-page review is tied to the exact audited source hash.

Use `Retriever.page_context(hit_metadata)` to recover the full cited page when conditions span chunks.

Do not infer an exemption, current commencement date, or complete applicable standards list from one fragment. Retrieve and inspect the relevant order/amendment chain. The uploaded manual identifies PM/9873/14, May 2026. Later official publications may exist outside this dataset.

## Retrieval quality gate

`evaluation/questions.json` contains ten evidence-location checks. `retrieval/test_retrieval.py` writes full passages, distances and timings to `evaluation/retrieval_results.json`, and exits nonzero for a missing expected source/page. An evidence hit is not proof that every condition needed for an answer is present. Review each saved result for complete conditions, authoritative source, correct citation and conflicting amendments. Add reviewer judgments before enabling automatic compliance answers.

The first query includes model startup time; subsequent query timings are warm. These results are a small diagnostic set, not a production performance benchmark. Do not loosen expected pages simply to make tests pass.

## Team handoff

Commit regenerated outputs and validation/evaluation reports together with pipeline changes. Do not commit `venv`, credentials, model caches or `data/chroma`. Each teammate rebuilds their own local index. Merge the reviewed repair branch into `main` so default clones receive the active pipeline; old `data` branch commands remain historical until updated.
