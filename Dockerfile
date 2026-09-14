FROM python:3.11.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/models/huggingface \
    HUGGINGFACE_HUB_CACHE=/opt/models/huggingface/hub

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# The service is CPU-only.  Install the same pinned Torch release from the
# official CPU wheel index before the remaining pinned requirements, avoiding
# unused CUDA runtime libraries in this portability image.
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.5.1+cpu \
    && python -m pip install --no-cache-dir -r requirements.txt

# The embedding contract in retrieval/embeddings.py is the source of truth.
# This deliberately fails the build if the immutable revision is unavailable.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small', revision='614241f622f53c4eeff9890bdc4f31cfecc418b3')"

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY backend ./backend
COPY retrieval ./retrieval
COPY scripts/container_healthcheck.py ./scripts/container_healthcheck.py
COPY data/raw ./data/raw
COPY data/processed/generated_v3 ./data/processed/generated_v3
COPY data/chroma ./data/chroma

RUN groupadd --gid 10001 bis \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin bis \
    && chown -R bis:bis /app /opt/models

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 CMD ["python", "scripts/container_healthcheck.py"]

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
