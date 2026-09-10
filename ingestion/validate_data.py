"""Integrity gates; raises even when Python runs with -O."""
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/processed/generated_v3'
def require(condition, message):
    if not condition: raise ValueError(message)
def digest(data): return hashlib.sha256(data).hexdigest()
def validate(data=DATA):
    from pypdf import PdfReader
    from transformers import AutoTokenizer
    manifest = json.loads((data/'embedding_manifest.json').read_text(encoding='utf-8'))
    tokenizer = AutoTokenizer.from_pretrained(manifest['model'],revision=manifest['model_revision'])
    sources = json.loads((data/'source_registry.json').read_text(encoding='utf-8'))
    pages = [json.loads(x) for x in (data/'pages.jsonl').read_text(encoding='utf-8').splitlines()]
    chunks = [json.loads(x) for x in (data/'chunks.jsonl').read_text(encoding='utf-8').splitlines()]
    require(digest((data/'chunks.jsonl').read_bytes()) == manifest['chunks_sha256'],'Chunks hash mismatch')
    require({p.name for p in (ROOT/'data/raw').glob('*.pdf')} == {s['source_filename'] for s in sources},'Raw inventory mismatch')
    source_map = {s['source_id']:s for s in sources}
    require(len(source_map)==len(sources), 'Duplicate source IDs')
    expected_pages = set()
    for s in sources:
        path = ROOT/s['source_path']
        require(digest(path.read_bytes())==s['source_sha256'],'Raw source changed: '+path.name)
        require(len(PdfReader(path).pages)==s['page_count'],'Physical page count mismatch')
        expected_pages.update((s['source_id'],p) for p in range(1,s['page_count']+1))
    page_map = {(p['source_id'],p['page_number']):p for p in pages}
    require(len(page_map)==len(pages) and set(page_map)==expected_pages,'Page coverage mismatch')
    ids = {c['id'] for c in chunks}
    require(len(ids)==len(chunks),'Duplicate chunk IDs')
    referenced = set()
    for p in pages:
        require(not p['clean_text'] or bool(p['chunk_ids']),'Nonempty page missing chunks')
        require(set(p['chunk_ids'])<=ids,'Page references missing chunks')
        referenced.update(p['chunk_ids'])
    require(referenced==ids,'Orphan chunks')
    for c in chunks:
        m=c['metadata']; doc=c['document']; s=source_map[m['source_id']]
        require(all(type(v) in (str,int,float,bool) for v in m.values()),'Invalid Chroma metadata')
        require(all(m[k]==s[k] for k in ('source_filename','source_path','source_sha256')),'Chunk source provenance mismatch')
        require(m['dataset_version']==manifest['dataset_version'],'Dataset mismatch')
        require(1<=m['page_start']==m['page_end']<=s['page_count'],'Invalid citation page')
        p=page_map[m['source_id'],m['page_start']]
        require(c['id'] in p['chunk_ids'],'Incorrect page reference')
        require(p['source_sha256']==s['source_sha256'],'Page source hash mismatch')
        require(doc.startswith('passage: ') and len(doc)>9,'Empty or unprefixed document')
        require(digest(doc.encode())==m['text_sha256'] and len(doc)==m['char_count'],'Text integrity mismatch')
        require(len(tokenizer.encode(doc))==m['token_count']<=480,'Token budget mismatch')
        if m['chunk_type']=='document_text':
            require(' '.join(doc[9:].split()) in ' '.join(p['clean_text'].split()),'Ungrounded document text')
        require(not m['default_retrieval'] or m['retrieval_enabled'],'Invalid default flag')
        require(not m['retrieval_enabled'] or p['review_status']!='needs_review','Unreviewed low-quality page enabled')
    require(sum(c['metadata']['retrieval_enabled'] for c in chunks)==manifest['retrieval_chunk_count'],'Retrieval count mismatch')
    result={'sources':len(sources),'pages':len(pages),'chunks':len(chunks),'validation':'passed'}
    print(json.dumps(result)); return result
if __name__=='__main__': validate()
