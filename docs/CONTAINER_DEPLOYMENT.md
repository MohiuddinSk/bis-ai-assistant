# Backend container prototype

This is a self-contained SIH prototype image for portability validation. It is not a production-readiness statement, a BIS approval, or a nationwide deployment design. The image includes the authorized prototype corpus, so it must not be published to a public registry until distribution rights for every included artifact have been reviewed.

## Image strategy

The image is based on `python:3.11.14-slim-bookworm` (Debian Bookworm) and starts one Uvicorn worker. It contains only the backend and retrieval code, the authorized `data/raw` PDFs, `data/processed/generated_v3`, and the existing `data/chroma` index. It installs the project-pinned CPU PyTorch wheel (no unused CUDA runtime) and uses UID/GID `10001` (`bis`) rather than root, drops Linux capabilities in Compose, prevents privilege escalation, and has a private writable `/tmp` tmpfs.

The embedding model is downloaded during the image build into `/opt/models/huggingface`. The model identifier and immutable revision are taken from `retrieval/embeddings.py`: `intfloat/multilingual-e5-small` at `614241f622f53c4eeff9890bdc4f31cfecc418b3`. A failed download fails the build. At runtime `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` ensure SentenceTransformer loads that baked cache without a fresh network download. Host Hugging Face cache files are never copied.

The current Windows-generated Chroma index is copied solely for Linux compatibility validation. It is accepted only when the Linux container starts, reports the expected collection, and passes the retrieval-based acceptance checks. ChromaDB is not asserted as the final nationwide store.

## Local build and run

Docker Desktop with the Linux engine and enough disk/RAM for PyTorch and the model is required. The first build can take several minutes and the first process startup can take longer while Python and the embedding model initialize.

```powershell
docker build --tag bis-saarthi-backend:prototype .
docker compose up --build
```

The API is then at `http://127.0.0.1:8000`; stop it with:

```powershell
docker compose down
```

Compose supplies only non-secret defaults. Optional runtime variables, with no values shown here, are:

- `GROQ_API_KEY`
- `RETRIEVAL_PROVIDER` (`chroma_local` by default; `disabled` for no retrieval client)
- `LLM_PROVIDER` (`groq`, `openai_compatible`, or `disabled`)
- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_MAX_COMPLETION_TOKENS`
- `LLM_STRUCTURED_OUTPUT_MODE` (`json_schema` or `json_object`)
- `LLM_ALLOWED_HOSTS`
- `ALLOWED_ORIGINS`

`GROQ_API_KEY` is interpolated only at runtime and is intentionally empty by default. Do not put credentials in `compose.yaml`, the Dockerfile, image labels, or build arguments. The Compose syntax does not set CPU or memory limits because ordinary local Compose runs do not consistently enforce `deploy.resources`; apply platform-controlled limits in a managed target if needed.

Groq remains the compatible default. `disabled` keeps retrieval and deterministic answers available but returns the existing sanitized generation-unavailable response only for questions that genuinely require model generation. An OpenAI-compatible endpoint is administrator configuration only: its absolute base URL must be allowlisted by exact `LLM_ALLOWED_HOSTS`; HTTPS is required except explicit allowlisted loopback development hosts. No provider URL or key is accepted from callers. Use network egress allowlisting in BIS/NIC deployment; DNS-rebinding and network routing controls remain deployment responsibilities. Provider portability does not make Chroma or the prototype data infrastructure production-ready, and this remains neither BIS nor NIC approval.

Retrieval and generation provider selection are independent. `RETRIEVAL_PROVIDER=chroma_local` is the current default and validated container mode; it uses the embedded Chroma index and offline E5 model. `RETRIEVAL_PROVIDER=disabled` starts without Chroma/E5 retrieval and therefore reports degraded health and the existing sanitized 503 retrieval/chat responses. No remote retrieval provider is implemented yet.

## Health and acceptance

Docker runs `scripts/container_healthcheck.py`, a standard-library probe of `/api/v1/health`. It requires HTTP success, `status: ready`, and a positive `collection_count`; it does not encode the current corpus count.

Run the portable local acceptance suite from PowerShell:

```powershell
.\scripts\test_container.ps1
```

This manual-only acceptance command requires Docker Desktop, the local read-only Chroma index, the committed generated-v3 artifacts, and the pinned E5 model assets required by the image build. It builds an isolated acceptance-tagged image and starts one uniquely named container. It validates health, legacy and versioned routes, retrieval, UID/GID `10001:10001`, disabled generation, and empty provider-key entries. Before and after execution it hashes `data/raw`, `data/processed`, `evaluation`, and `data/chroma`; any difference fails acceptance. It restores its process environment and removes only the container it created. It never deletes Docker volumes, unrelated containers, images, or repository data. This is intentionally manual and is not part of hosted pull-request CI.

For the narrow local image cleanup only:

```powershell
docker image rm bis-saarthi-backend:prototype
```

Run that command only after confirming no container still depends on this exact image tag. Do not use `docker system prune` for this prototype workflow.

## Data and portability considerations

The source registry and PDFs in the image are read-only runtime inputs; the image does not regenerate datasets or indexes. The application validates the generated-v3 manifest, model contract, chunk integrity, and collection IDs during retriever startup. A Linux build/start result is evidence only for this prototype data/index combination. If it fails, do not rebuild or substitute the protected corpus or model without explicit approval.

For a future BIS/NIC deployment, use approved read-only model artifacts, an auditable artifact-delivery path, and controlled persistent/index infrastructure with backups, access controls, lifecycle ownership, and migration testing. Revalidate source rights, document updates, model artifacts, and Chroma/index compatibility. This prototype makes no production, security-certification, availability, scale, or BIS-approval claim.

## Troubleshooting

- If Docker cannot build, confirm Docker Desktop is running the Linux engine and can access the Python package and Hugging Face registries. The pinned model revision must not be changed or replaced.
- If health remains `starting` or `unhealthy`, inspect only bounded logs from the test container or `docker compose logs backend`; do not put credentials in diagnostic commands.
- If the index is unavailable in Linux, record the startup error and preserve the protected data. Treat that as failed portability validation rather than modifying retrieval behavior.
- If port 8000 is occupied, use `./scripts/test_container.ps1 -HostPort 18001` for the acceptance test, or adjust only the host-side Compose mapping.
