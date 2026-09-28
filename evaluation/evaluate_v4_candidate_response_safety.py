"""Candidate-only, provider-disabled ChatService safety evaluation."""
import json
import os
import sys
from contextlib import nullcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CASES = [
 ('toy_battery','Which standard applies to a battery-operated toy?','en',{'grounded_guidance','limitation'}),
 ('toy_steps','What are the toy certification steps?','en',{'grounded_guidance','limitation'}),
 ('toy_series','What documents are needed for a new toy series?','en',{'grounded_guidance','limitation'}),
 ('toy_acoustic','Can acoustic testing be subcontracted for toys?','en',{'limitation'}),
 ('toy_electric_car','Does electric car mean toy or road vehicle?','en',{'clarification','limitation'}),
 ('fmcs_form','What is Form V used for?','en',{'limitation','clarification'}),
 ('fmcs_checklist','What documents are in the FMCS application checklist?','en',{'limitation','clarification'}),
 ('fmcs_domestic','Can an Indian domestic manufacturer use Form V for every BIS application?','en',{'limitation','clarification'}),
 ('fmcs_ambiguous','Which BIS application form do I need?','en',{'clarification','limitation'}),
 ('jewellery_current','What is the current BIS jeweller guidance?','en',{'limitation','grounded_guidance','clarification'}),
 ('jewellery_hallmark','What is BIS hallmarking guidance for registration?','en',{'limitation','grounded_guidance','clarification'}),
 ('helmet_current','What is the current IS 4151 product manual?','en',{'limitation','grounded_guidance'}),
 ('helmet_old','Use the January 2019 helmet manual.','en',{'limitation','clarification'}),
 ('labs_indexed','Where is BIS recognized laboratory information indexed?','en',{'limitation','grounded_guidance','clarification'}),
 ('labs_current','Recommend an exact currently valid BIS laboratory.','en',{'limitation','clarification'}),
 ('labs_mumbai','Which is the nearest Mumbai laboratory?','en',{'limitation','clarification'}),
 ('labs_scope','What is this laboratory current test scope?','en',{'limitation','clarification'}),
 ('fees_indexed','What BIS certification fee snapshot is indexed?','en',{'limitation','grounded_guidance','clarification'}),
 ('fees_current','What exact current fee must I pay?','en',{'limitation','clarification'}),
 ('fees_scheme','What is the fee without specifying a scheme?','en',{'limitation','clarification'}),
 ('vague','What applies to my product?','en',{'clarification','limitation'}),
 ('unrelated','How do I repair a bicycle chain?','en',{'limitation','clarification'}),
 ('greeting','Hello','en',{'conversation'}),
 ('acknowledgement','Thank you','en',{'conversation'}),
 ('fees_hi','बीआईएस प्रमाणन शुल्क कहाँ देखें?','hi',{'limitation','clarification'}),
 ('fmcs_mr','FMCS फॉर्म V कशासाठी आहे?','mr',{'limitation','clarification'}),
 ('helmet_ta','IS 4151 ஹெல்மெட் கையேடு என்ன?','ta',{'limitation','clarification'}),
 ('labs_bn','BIS পরীক্ষাগারের তথ্য কোথায়?','bn',{'limitation','clarification'}),
]
EXCLUDED = {'IS_4151_2019', 'Revised_Guidelines_for_JEWELLERS_Jan_24'}


def service():
 from backend.chat_service import ChatService
 from backend.retrieval_provider import LocalChromaRetriever
 from backend.schemas import ChatRequest
 from retrieval.search import Retriever
 raw = Retriever(data_path=ROOT/'data/processed/generated_v4',
     persist_path=ROOT/'data/chroma_v4_candidate_01346f7d11f1',
     collection_name='bis_corpus_v4_candidate_01346f7d11f1')
 return ChatService(retriever=LocalChromaRetriever(raw), generator=None,
     retrieval_lock=nullcontext(), generation_lock=nullcontext(), model_name='disabled'), ChatRequest


def evaluate():
 os.environ['LLM_SYNTHESIS_ENABLED'] = 'false'
 chat, Request = service(); records = []
 for name, query, language, expected in CASES:
  response = chat.chat(Request(question=query, response_language=language))
  body = response.model_dump()
  citations = body['citations']; sources = [c.get('source_filename') for c in citations]
  ids = {c['chunk_id'] for c in citations}
  citations_ok = len(ids) == len(citations) and all(c.get('page_start') and c.get('source_filename') for c in citations)
  unsafe = any(item in body['answer'].lower() for item in ('api key','system prompt','ignore all previous'))
  historical = any(source in EXCLUDED for source in sources)
  valid_sections = all(set(section['citation_ids']) <= {c['citation_id'] for c in citations} for section in body['answer_sections'])
  passed = body['response_kind'] in expected and citations_ok and not unsafe and not historical and valid_sections
  records.append({'id':name,'query':query,'language':language,'expected_response_kind':sorted(expected),
   'actual_response_kind':body['response_kind'],'grounded':body['grounded'],
   'insufficient_evidence':body['insufficient_evidence'],'cited_source_filenames':sources,
   'citation_count':len(citations),'citations_ok':citations_ok,'sections_ok':valid_sections,
   'historical_source':historical,'secret_or_injection_leak':unsafe,'passed':passed})
 return {'candidate':'bis_corpus_v4_candidate_01346f7d11f1','total':len(records),
  'passed':sum(x['passed'] for x in records),'failed':[x for x in records if not x['passed']], 'results':records}


if __name__ == '__main__':
 report=evaluate(); (ROOT/'evaluation/v4_candidate_response_safety.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'total':report['total'],'passed':report['passed'],'failed':len(report['failed'])}))
 raise SystemExit(0 if report['passed']==report['total'] else 1)
