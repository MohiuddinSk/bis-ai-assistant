"""One explicit embedding contract shared by ingestion and search."""
from functools import lru_cache
MODEL = 'intfloat/multilingual-e5-small'
REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
MAX_TOKENS = 512

@lru_cache(maxsize=1)
def model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL, revision=REVISION)

def encode(texts, kind):
    if kind not in ('query', 'passage'):
        raise ValueError('Invalid embedding kind')
    prefix = kind + ': '
    prepared = [t if t.startswith(prefix) else prefix + t for t in texts]
    encoder = model()
    lengths = [len(encoder.tokenizer.encode(t)) for t in prepared]
    if any(n > MAX_TOKENS for n in lengths):
        raise ValueError('Text exceeds E5 token limit; re-chunk instead of truncating')
    return encoder.encode(prepared, normalize_embeddings=True, convert_to_numpy=True).tolist()
