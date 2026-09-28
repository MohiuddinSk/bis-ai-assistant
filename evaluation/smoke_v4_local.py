"""Local-only API smoke for an explicitly selected V4 container."""
import json, sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
CASES=[
 ('hi','Hi',{'conversation'}),('okay','Okay',{'conversation'}),('capabilities','What can you help me with?',{'conversation'}),
 ('battery','Which standard applies to a battery-operated toy?',{'grounded_guidance','limitation'}),('parts','What is IS 9873?',{'grounded_guidance','limitation','clarification'}),
 ('steps','What are toy certification steps?',{'grounded_guidance','limitation'}),('series','documents for a new toy series',{'grounded_guidance','limitation'}),('age','higher age grading for toys',{'grounded_guidance','limitation'}),('acoustic','Can acoustic testing be subcontracted?',{'limitation','clarification'}),
 ('form','What is Form V used for?',{'limitation','clarification'}),('checklist','FMCS application checklist',{'limitation','clarification'}),('domestic','Can a domestic manufacturer use Form V for every BIS application?',{'limitation','clarification'}),
 ('jewellery','current jeweller guidance',{'limitation','clarification','grounded_guidance'}),('helmet','current IS 4151 helmet manual',{'limitation','clarification','grounded_guidance'}),
 ('lab','recommend a current Mumbai laboratory',{'limitation','clarification'}),('fee','what exact current certification fee must I pay?',{'limitation','clarification'}),
 ('ambiguous_form','Which application form do I need?',{'limitation','clarification'}),('vague','What applies to my product?',{'clarification'}),
 ('hi_fee','बीआईएस प्रमाणन शुल्क कहाँ देखें?',{'limitation','clarification'}),('mr_form','FMCS फॉर्म V कशासाठी आहे?',{'limitation','clarification'}),('ta_helmet','IS 4151 ஹெல்மெட் கையேடு என்ன?',{'limitation','clarification','grounded_guidance'}),('bn_lab','BIS পরীক্ষাগারের তথ্য কোথায়?',{'limitation','clarification'}),]
def main():
 base=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8001'; records=[]
 for name,q,expected in CASES:
  req=Request(base+'/api/v1/chat',data=json.dumps({'question':q}).encode(),headers={'Content-Type':'application/json'})
  with urlopen(req,timeout=30) as r: body=json.load(r); status=r.status
  citations=body.get('citations',[]); safe=not any(x in body.get('answer','').lower() for x in ('api key','system prompt','ignore all previous'))
  record={'id':name,'status':status,'response_kind':body.get('response_kind'),'grounded':body.get('grounded'),'insufficient_evidence':body.get('insufficient_evidence'),'citation_chunk_ids':[c.get('chunk_id') for c in citations],'citation_sources':[c.get('source_filename') for c in citations]}
  record['passed']=status==200 and record['response_kind'] in expected and safe; records.append(record)
 report={'base_url':base,'total':len(records),'passed':sum(r['passed'] for r in records),'failed':[r for r in records if not r['passed']],'results':records}
 print(json.dumps({'total':report['total'],'passed':report['passed'],'failed':report['failed']})); return 0 if report['total']==report['passed'] else 1
if __name__=='__main__': raise SystemExit(main())
