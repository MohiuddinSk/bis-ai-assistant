"""Candidate-only retrieval evaluation using the production E5 query contract."""
import argparse,json,hashlib,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
def retrieve(retriever, query, k=10):
 """Evaluation wrapper: deliberately delegates ranking to public production search."""
 return retriever.search(query,k=k)
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--persist',required=True);p.add_argument('--collection',required=True);p.add_argument('--cases',default=str(ROOT/'evaluation/v4_retrieval_cases.json'));p.add_argument('--out',default=str(ROOT/'evaluation/v4_retrieval_report.json'));a=p.parse_args(argv)
 from retrieval.search import Retriever
 r=Retriever(data_path=ROOT/'data/processed/generated_v4',persist_path=a.persist,collection_name=a.collection); cases=json.loads(Path(a.cases).read_text()); results=[]
 for case in cases:
  raw=retrieve(r,case['query'],k=10); metas=raw['metadatas'][0]; sources=[m.get('source_id') for m in metas]; expected=set(case.get('expected_sources',[])); rank=next((i+1 for i,s in enumerate(sources) if s in expected),None) if expected else None
  forbidden=set(case.get('forbidden_sources',[]))&set(sources); meta_ok=all(any(all(m.get(k)==v for k,v in case.get('metadata',{}).items()) for m in metas if m.get('source_id') in expected) for _ in [0]) if expected else True
  passed=(not expected or rank is not None) and not forbidden and meta_ok
  ranking=[{'rank':i+1,'source_id':m.get('source_id'),'category':m.get('category','v3_toys'),'page':m.get('page_start'),'chunk_id':raw['ids'][0][i],'distance':raw['distances'][0][i],'title':raw['documents'][0][i][:100]} for i,m in enumerate(metas)]; results.append({**case,'sources':sources,'ranking':ranking,'rank':rank,'passed':passed,'forbidden':sorted(forbidden),'metadata_ok':meta_ok})
 pos=[x for x in results if x.get('expected_sources')]; group=lambda key:{f'{name}:pass' if ok else f'{name}:fail':n for (name,ok),n in Counter((x[key],x['passed']) for x in results).items()}; report={'candidate':a.collection,'total':len(results),'passed':sum(x['passed'] for x in results),'failed':[x for x in results if not x['passed']],'top1':sum(x['rank']==1 for x in pos)/len(pos),'top3':sum(bool(x['rank'] and x['rank']<=3) for x in pos)/len(pos),'top5':sum(bool(x['rank']) for x in pos)/len(pos),'mrr':sum(1/x['rank'] if x['rank'] else 0 for x in pos)/len(pos),'by_category':group('category'),'by_language':group('language'),'results':results}
 Path(a.out).write_text(json.dumps(report,indent=2,ensure_ascii=False,sort_keys=True)+'\n'); print(json.dumps({k:report[k] for k in ('total','passed','top1','top3','top5','mrr')},sort_keys=True)); return 0 if report['passed']==report['total'] else 1
if __name__=='__main__':raise SystemExit(main())
