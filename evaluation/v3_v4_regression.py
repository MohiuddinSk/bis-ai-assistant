"""Read-only public-Retriever toy regression comparison."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrieval.search import Retriever
CASES=[
 ('battery-operated toy standard',{'product_manual_2026'},'IS 15644'),
 ('IS 9873 toy',{'product_manual_2026','Toy_QC_order'},'IS 9873'),
 ('toy certification steps',{'product_manual_2026'},None),
 ('documents for new toy series',{'product_manual_2026'},None),
 ('2026 transition order',{'Notification_of_Transition_Facilitation_Quality_Control_Order_2026'},None),
 ('higher age toy grading',{'product_manual_2026'},None),
]
def ids(r,q):
 raw=r.search(q,k=5);return [{'id':raw['ids'][0][i],'source_id':raw['metadatas'][0][i].get('source_id'),'page':raw['metadatas'][0][i].get('page_start'),'source_filename':raw['metadatas'][0][i].get('source_filename'),'text':raw['documents'][0][i]} for i in range(5)]
def main():
 v3=Retriever();v4=Retriever(data_path=ROOT/'data/processed/generated_v4',persist_path=ROOT/'data/chroma_v4_candidate_01346f7d11f1',collection_name='bis_corpus_v4_candidate_01346f7d11f1'); rows=[]
 for q,expected,identifier in CASES:
  a,b=ids(v3,q),ids(v4,q); sources=[x['source_id'] for x in b]
  first=next((i+1 for i,s in enumerate(sources) if s in expected),None)
  forbidden=[x for x in b if x['source_id'] in {'IS_4151_2019','Revised_Guidelines_for_JEWELLERS_Jan_24'}]
  metadata_ok=all(x['id'] and x['source_id'] and x['page'] and x['source_filename'] for x in b)
  v3_identifier_present=not identifier or any(identifier.lower() in x['text'].lower() for x in a)
  v4_identifier_present=not identifier or any(identifier.lower() in x['text'].lower() for x in b)
  identifier_preserved=(not v3_identifier_present) or v4_identifier_present
  rows.append({'query':q,'expected_sources':sorted(expected),'required_identifier':identifier,'v3_top5':a,'v4_top5':b,'first_relevant_rank':first,'forbidden':forbidden,'metadata_ok':metadata_ok,'v3_identifier_present':v3_identifier_present,'v4_identifier_present':v4_identifier_present,'identifier_preserved':identifier_preserved,'pass':bool(first and metadata_ok and identifier_preserved and not forbidden)})
 report={'total':len(rows),'passed':sum(x['pass'] for x in rows),'failed':[x for x in rows if not x['pass']],'results':rows};(ROOT/'evaluation/v3_v4_regression.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({key:report[key] for key in ('total','passed','failed')}));return 0 if report['passed']==report['total'] else 1
if __name__=='__main__':raise SystemExit(main())
