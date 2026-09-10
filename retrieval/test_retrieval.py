"""Persist retrieval results and fail on missing expected evidence."""
import json
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from retrieval.search import Retriever
if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')

def main():
    cases=json.loads((ROOT/'evaluation/questions.json').read_text(encoding='utf-8'))
    searcher=Retriever()
    reports=[]
    for case in cases:
        started=time.perf_counter()
        result=searcher.search(case['question'],include_guidance=case.get('include_guidance',False))
        hits=[{'id':i,'document':d,'metadata':m,'distance':s} for i,d,m,s in zip(result['ids'][0],result['documents'][0],result['metadatas'][0],result['distances'][0])]
        matched=any(any(h['metadata']['source_filename']==e['source'] and (not e.get('pages') or h['metadata']['page_start'] in e['pages']) for e in case['expected_evidence']) for h in hits)
        reports.append({'id':case['id'],'question':case['question'],'evidence_hit_at_5':matched,
            'elapsed_ms':round((time.perf_counter()-started)*1000,2),'hits':hits,
            'human_relevance':'pending','notes':'Evidence-location check does not validate a legal conclusion.'})
        print(f"{case['id']}: {'PASS' if matched else 'FAIL'} ({len(hits)} hits)")
    out=ROOT/'evaluation/retrieval_results.json'
    out.write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Evidence hit rate: {sum(r["evidence_hit_at_5"] for r in reports)}/{len(reports)}')
    if not all(r['evidence_hit_at_5'] for r in reports): raise SystemExit(1)
if __name__=='__main__': main()
