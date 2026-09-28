# Local V4 promotion and rollback

V3: `RETRIEVAL_CORPUS_VERSION=v3`, `data/processed/generated_v3`, `data/chroma`, `bis_toys_v3_e73aab14a72f7908_39b347ab687e` (917).

V4: `RETRIEVAL_CORPUS_VERSION=v4_01346f7d11f1`, `data/processed/generated_v4`, `data/chroma_v4_01346f7d11f1`, `bis_corpus_v4_candidate_01346f7d11f1` (1,160).

```powershell
docker run --rm -p 127.0.0.1:8001:8000 -e RETRIEVAL_PROVIDER=chroma_local -e RETRIEVAL_CORPUS_VERSION=v4_01346f7d11f1 -e LLM_PROVIDER=disabled bis-saarthi-backend:v4-01346f7d11f1
Invoke-RestMethod http://127.0.0.1:8001/api/v1/health
```

Expected V4 health is `ready` / 1,160. Rollback starts a separately named local container with `RETRIEVAL_CORPUS_VERSION=v3`; expected health count is 917. Never overwrite `data/chroma`, the immutable candidate, or blocked `f899313eaaac`. Take a reviewed V3 backup before any public activation.

The factory deliberately injects a configured, manifest-validated `Retriever` into `LocalChromaRetriever`; its constructor officially supports this dependency.
