"""Deterministically combine immutable V3 with approved V4 additions only."""
from __future__ import annotations
import hashlib,json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; V3=ROOT/'data/processed/generated_v3'; V4=ROOT/'data/processed/generated_v4'
def rows(path): return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x]
def dump(path, values): path.write_text(''.join(json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n' for x in values),encoding='utf-8')
def hash_file(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 v3pages,v3chunks=rows(V3/'pages.jsonl'),rows(V3/'chunks.jsonl'); v4pages,v4chunks=rows(V4/'pages.jsonl'),rows(V4/'chunks.jsonl'); v3reg=json.loads((V3/'source_registry.json').read_text()); v4reg=json.loads((V4/'source_registry.json').read_text())
 complete=v3chunks+v4chunks; ids=[x['id'] for x in complete]
 if len(ids)!=len(set(ids)): raise ValueError('duplicate complete chunk IDs')
 source_ids={x['metadata']['source_id'] for x in complete}; expected={x['source_id'] for x in v3reg}|{x['source_id'] for x in v4reg}
 if source_ids!=expected or len(expected)!=15: raise ValueError('complete source membership mismatch')
 if not {"fmcs_application_form_v","fmcs_application_checklist"}<={x['metadata']['source_id'] for x in v4chunks}: raise ValueError('FMCS additions absent')
 if {x['id'] for x in v3chunks}-{x['id'] for x in complete}: raise ValueError('V3 identity loss')
 dump(V4/'pages_complete.jsonl',v3pages+v4pages); dump(V4/'chunks_complete.jsonl',complete); (V4/'source_registry_complete.json').write_text(json.dumps(v3reg+v4reg,indent=2,ensure_ascii=False,sort_keys=True)+'\n',encoding='utf-8')
 report={'v3':{'sources':len(v3reg),'pages':len(v3pages),'chunks':len(v3chunks),'chunks_sha256':hash_file(V3/'chunks.jsonl')},'v4_additions':{'sources':len(v4reg),'pages':len(v4pages),'chunks':len(v4chunks)},'complete_v4':{'sources':len(expected),'pages':len(v3pages)+len(v4pages),'chunks':len(complete),'unique_ids':len(set(ids))},'source_ids':sorted(expected),'per_source_chunks':dict(sorted(Counter(x['metadata']['source_id'] for x in complete).items())),'per_category_chunks':dict(sorted(Counter(x['metadata'].get('category','v3_toys') for x in complete).items()))}
 (V4/'complete_v4_composition_report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(json.dumps(report,sort_keys=True))
if __name__=='__main__':main()
