from pathlib import Path
import json
import hashlib
import re
from retrieval.embeddings import encode, MODEL, REVISION
ROOT = Path(__file__).resolve().parents[1]

class Retriever:
    def __init__(self):
        import chromadb
        from chromadb.config import Settings
        data = ROOT / 'data/processed/generated_v3'
        manifest = json.loads((data / 'embedding_manifest.json').read_text(encoding='utf-8'))
        if (manifest['model'], manifest['model_revision']) != (MODEL, REVISION):
            raise ValueError('Embedding contract mismatch')
        self.pages = {(p['source_id'], p['page_number']): p for p in
            (json.loads(x) for x in (data/'pages.jsonl').read_text(encoding='utf-8').splitlines())}
        self.client = chromadb.PersistentClient(path=str(ROOT / 'data/chroma'), settings=Settings(anonymized_telemetry=False))
        self.collection = self.client.get_collection(manifest['collection_name'], embedding_function=None)
        for key in ('dataset_version', 'model', 'model_revision'):
            if self.collection.metadata.get(key) != manifest[key]:
                raise ValueError('Collection contract mismatch')
        raw = (data / 'chunks.jsonl').read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest['chunks_sha256']:
            raise ValueError('Chunk-file integrity mismatch')
        rows = [json.loads(x) for x in raw.decode('utf-8').splitlines()]
        expected = {r['id'] for r in rows if r['metadata']['retrieval_enabled']}
        if set(self.collection.get(include=[])['ids']) != expected:
            raise ValueError('Incomplete or contaminated collection; rebuild first')

    def search(self, question, k=5, include_guidance=False):
        if not question.strip() or k < 1:
            raise ValueError('A nonempty query and positive k are required')
        candidate_k = min(max(k * 20, 100), self.collection.count())
        raw = self.collection.query(query_embeddings=encode([question], 'query'), n_results=candidate_k,
            where={'retrieval_enabled': True} if include_guidance else {'default_retrieval': True},
            include=['documents', 'metadatas', 'distances'])
        stop = {'which','what','does','the','a','an','is','are','can','for','of','to','and','in','on','i','do','all','latest','available'}
        terms = {x for x in re.findall(r'[a-z0-9]+', question.lower()) if len(x)>2 and x not in stop}
        synonyms = {'handmade': {'artisan','artisans','handicraft'}, 'exempt': {'apply','excludes','exclusion'},
                    'rattle': {'rattle'}, 'commencement': {'force','effective','january'}}
        for term, expansions in synonyms.items():
            if term in terms: terms.update(expansions)
        scored=[]
        for i,(doc,meta,distance) in enumerate(zip(raw['documents'][0],raw['metadatas'][0],raw['distances'][0])):
            words=set(re.findall(r'[a-z0-9]+', doc.lower()))
            lexical=len(terms & words) / max(1,len(terms))
            # Keep vector similarity dominant; lexical overlap breaks close ties.
            score=(1.0-float(distance)) + 0.35*lexical
            scored.append((score,i))
        scored.sort(reverse=True)
        keep=[i for _,i in scored[:k]]
        result = {}
        for key, value in raw.items():
            if value is None:
                result[key] = None
            elif isinstance(value, list) and value and isinstance(value[0], list):
                result[key] = [[value[0][i] for i in keep]]
            else:
                result[key] = value
        return result

    def page_context(self, metadata):
        """Return the full cited page for checking split conditions, with provenance."""
        page = self.pages[(metadata['source_id'], metadata['page_start'])]
        return {'source_filename': page['source_filename'], 'page_number': page['page_number'],
            'source_sha256': page['source_sha256'], 'text': page['clean_text']}
