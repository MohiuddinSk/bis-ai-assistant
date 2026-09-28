from pathlib import Path
import json
import hashlib
import re
import logging
from retrieval.embeddings import encode, MODEL, REVISION
from retrieval.hybrid_rerank import intents, rerank
ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


def validate_embedding_manifest(manifest):
    """Strictly recognise only the established V3 or canonical V4 contracts."""
    is_v4 = manifest.get('schema_version') == 'v4_embedding_manifest/1'
    if manifest.get('schema_version') and not is_v4:
        raise ValueError('Unsupported embedding manifest schema')
    required = (
        'model', 'model_revision', 'dimension', 'normalize_embeddings',
        'distance', 'query_prefix', 'passage_prefix', 'corpus_sha256',
        'chunk_count', 'source_artifact',
    ) if is_v4 else ('model', 'model_revision', 'dataset_version', 'chunks_sha256')
    missing = [key for key in required if key not in manifest]
    if missing:
        raise ValueError('Embedding manifest missing required fields: ' + ', '.join(missing))
    if (manifest['model'], manifest['model_revision']) != (MODEL, REVISION):
        raise ValueError('Embedding contract mismatch')
    if is_v4 and (manifest['dimension'] != 384 or manifest['normalize_embeddings'] is not True
                  or manifest['distance'] != 'cosine' or manifest['query_prefix'] != 'query: '
                  or manifest['passage_prefix'] != 'passage: '):
        raise ValueError('V4 embedding manifest contract mismatch')
    return 'v4' if is_v4 else 'v3'

class Retriever:
    def __init__(self, data_path=None, persist_path=None, collection_name=None):
        import chromadb
        from chromadb.config import Settings
        data = Path(data_path) if data_path else ROOT / 'data/processed/generated_v3'
        manifest = json.loads((data / 'embedding_manifest.json').read_text(encoding='utf-8'))
        is_v4 = validate_embedding_manifest(manifest) == 'v4'
        self.pages = {(p['source_id'], p['page_number']): p for p in
            (json.loads(x) for x in (data/'pages.jsonl').read_text(encoding='utf-8').splitlines())}
        self.client = chromadb.PersistentClient(path=str(persist_path or ROOT / 'data/chroma'), settings=Settings(anonymized_telemetry=False))
        self.collection = self.client.get_collection(collection_name or manifest['collection_name'], embedding_function=None)
        for key in ('model', 'model_revision'):
            if self.collection.metadata.get(key) != manifest[key]:
                raise ValueError('Collection contract mismatch')
        raw = (data / ('chunks_complete.jsonl' if (data/'chunks_complete.jsonl').exists() else 'chunks.jsonl')).read_bytes()
        if not is_v4 and hashlib.sha256(raw).hexdigest() != manifest['chunks_sha256']:
            raise ValueError('Chunk-file integrity mismatch')
        if is_v4 and hashlib.sha256(raw).hexdigest()!=manifest['corpus_sha256']: raise ValueError('V4 chunk-file integrity mismatch')
        rows = [json.loads(x) for x in raw.decode('utf-8').splitlines()]
        if is_v4 and len(rows) != manifest['chunk_count']:
            raise ValueError('V4 chunk-count integrity mismatch')
        self.chunks_by_id = {row['id']: row for row in rows}
        self.page_chunk_ids = {}
        for row in rows:
            metadata = row['metadata']
            key = (metadata.get('source_id'), metadata.get('page_start'))
            self.page_chunk_ids.setdefault(key, []).append(row['id'])
        expected = {r['id'] for r in rows if r['metadata'].get('retrieval_enabled', True)}
        if set(self.collection.get(include=[])['ids']) != expected:
            raise ValueError('Incomplete or contaminated collection; rebuild first')

    def search(self, question, k=5, include_guidance=False):
        if not question.strip() or k < 1:
            raise ValueError('A nonempty query and positive k are required')
        candidate_k = min(max(k * 20, 100), self.collection.count())
        where={'retrieval_enabled': True} if include_guidance else {'default_retrieval': True}
        raw = self.collection.query(query_embeddings=encode([question], 'query'), n_results=candidate_k,
            where=where,
            include=['documents', 'metadatas', 'distances'])
        rows=[{'id':raw['ids'][0][i],'document':raw['documents'][0][i],'metadata':raw['metadatas'][0][i],'distance':raw['distances'][0][i]} for i in range(len(raw['ids'][0]))]
        for category in intents(question)[:3]:
            try:
                extra=self.collection.query(query_embeddings=encode([question],'query'),n_results=min(30,self.collection.count()),where={'$and':[where,{'category':category}]},include=['documents','metadatas','distances'])
            except Exception:
                continue
            rows.extend({'id':extra['ids'][0][i],'document':extra['documents'][0][i],'metadata':extra['metadatas'][0][i],'distance':extra['distances'][0][i]} for i in range(len(extra['ids'][0])))
        rows=rerank(question,list({row['id']:row for row in rows}.values()))[:k]
        return {'ids':[[x['id'] for x in rows]],'documents':[[x['document'] for x in rows]],'metadatas':[[x['metadata'] for x in rows]],'distances':[[x['distance'] for x in rows]]}
        stop = {'which','what','does','the','a','an','is','are','can','for','of','to','and','in','on','i','do','all','latest','available'}
        terms = {x for x in re.findall(r'[a-z0-9]+', question.lower()) if len(x)>2 and x not in stop}
        # Chat retrieval uses lexical coverage as a tie-breaker so qualifications and
        # standards named in a question survive vector-only ranking.  This does not
        # alter the generated_v3 data or the embedding collection.
        synonyms = {
            'electric': {'battery', 'operated', 'electrical'},
            'battery': {'electric', 'electrical'},
            'operated': {'electric', 'battery'},
            'handmade': {'artisan','artisans','handicraft'},
            'artisan': {'artisans', 'handicraft', 'registered'},
            'exempt': {'exemption', 'apply', 'excludes', 'exclusion'},
            'exemption': {'exempt', 'apply', 'excludes', 'exclusion'},
            'rattle': {'rattle'}, 'commencement': {'force','effective','january'},
        }
        for term, expansions in synonyms.items():
            if term in terms: terms.update(expansions)
        if any(term in question.lower() for term in ('electric toy', 'battery operated', 'is 15644', 'artisan', 'registered', 'handmade', 'exemption')):
            logger.info(
                'Chat retrieval lexical coverage enabled for grounding-sensitive terms; '
                'reason=retain standards and legal qualifications in final evidence'
            )
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

    def adjacent_chunks(self, chunk_id, source_id, page_start):
        """Return immediate same-page neighbours with stored provenance intact."""
        ids = self.page_chunk_ids.get((source_id, page_start), [])
        if chunk_id not in ids:
            return []
        index = ids.index(chunk_id)
        neighbours = []
        for neighbour_index in (index - 1, index + 1):
            if not 0 <= neighbour_index < len(ids):
                continue
            row = self.chunks_by_id[ids[neighbour_index]]
            metadata = row['metadata']
            neighbours.append({
                'chunk_id': row['id'], 'text': row['document'],
                'source_id': metadata.get('source_id'),
                'source_filename': metadata.get('source_filename'),
                'page_start': metadata.get('page_start'), 'page_end': metadata.get('page_end'),
                'chunk_type': metadata.get('chunk_type'),
            })
        return neighbours
