from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ingestion.validate_data import validate
from retrieval.embeddings import encode, MODEL, REVISION
DATA = ROOT / 'data/processed/generated_v3'

def main():
    import chromadb
    from chromadb.config import Settings
    validate(DATA)
    manifest = json.loads((DATA / 'embedding_manifest.json').read_text(encoding='utf-8'))
    if (manifest['model'], manifest['model_revision']) != (MODEL, REVISION):
        raise ValueError('Embedding contract differs from manifest')
    rows = [json.loads(line) for line in (DATA / 'chunks.jsonl').read_text(encoding='utf-8').splitlines()]
    rows = [r for r in rows if r['metadata']['retrieval_enabled']]
    expected = {r['id'] for r in rows}
    client = chromadb.PersistentClient(path=str(ROOT / 'data/chroma'), settings=Settings(anonymized_telemetry=False))
    collection = client.get_or_create_collection(manifest['collection_name'], embedding_function=None,
        metadata={'hnsw:space': 'cosine', 'dataset_version': manifest['dataset_version'], 'model': MODEL, 'model_revision': REVISION})
    for key in ('dataset_version', 'model', 'model_revision'):
        if collection.metadata.get(key) != manifest[key]:
            raise ValueError('Existing collection has incompatible metadata')
    existing = set(collection.get(include=[])['ids'])
    if existing - expected:
        raise ValueError('Unexpected IDs in dataset collection; refusing to mutate it')
    for start in range(0, len(rows), 64):
        batch = rows[start:start + 64]
        collection.upsert(ids=[r['id'] for r in batch], documents=[r['document'] for r in batch],
            metadatas=[r['metadata'] for r in batch], embeddings=encode([r['document'] for r in batch], 'passage'))
    if set(collection.get(include=[])['ids']) != expected:
        raise ValueError('Indexed IDs do not match dataset')
    print(json.dumps({'collection': collection.name, 'count': collection.count(), 'membership_verified': True}))

if __name__ == '__main__':
    main()
