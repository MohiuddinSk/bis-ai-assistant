"""Build the seven approved V4 additions; never reads or writes V3/Chroma."""
from __future__ import annotations
import hashlib, json, re
from collections import Counter
from pathlib import Path
from pypdf import PdfReader
try:
 from ingestion.fmcs_ocr_chunks import validate_chunk
except ModuleNotFoundError:  # direct CLI execution
 from fmcs_ocr_chunks import validate_chunk

ROOT=Path(__file__).resolve().parents[1]; RAW=ROOT/'data/raw'; OUT=ROOT/'data/processed/generated_v4'; OCR=OUT/'fmcs_ocr/chunks.jsonl'
CANON={
'fmcs/ApplicationFormV.pdf':dict(id='fmcs_application_form_v',category='fmcs',family='FMCS',scope='FMCS only',type='form',url='https://www.bis.gov.in/wp-content/uploads/2019/04/Application-Form-V.pdf',authority='BIS verified official',publication='April 2019',freshness='current_process_page_2026_05_12',live=False,default_retrieval=True,direct_recommendation_allowed=False,universal_claim_allowed=False),
'fmcs/Checklist_for_Application_for_BIS_Licence.pdf':dict(id='fmcs_application_checklist',category='fmcs',family='FMCS',scope='FMCS only',type='checklist',url='https://www.bis.gov.in/wp-content/uploads/2018/08/Checklist_for_Application.pdf',authority='BIS verified official',publication='August 2018',freshness='current_process_page_2026_05_12',live=False,default_retrieval=True,direct_recommendation_allowed=False,universal_claim_allowed=False),
'jewellery/Guidelines-for-Jewellers.pdf':dict(id='bis_jewellers_guidelines_2026',category='jewellery',family='hallmarking',scope='Jewellers Registration Scheme',type='guidance',url='https://www.bis.gov.in/wp-content/uploads/2026/07/Guidelines-for-Jewellers.pdf',authority='BIS verified official',publication='2 July 2026',freshness='current_2026_07_10',live=False,default_retrieval=True,direct_recommendation_allowed=True,universal_claim_allowed=False),
'laboratories/BIS_Recognised_LAB_Group_1.pdf':dict(id='bis_recognised_labs_group_1_2026_08_24',category='laboratories',family='laboratory_directory',scope='BIS recognised laboratory snapshot',type='laboratory_snapshot',url='https://lims.bis.gov.in/home/labs/',authority='BIS LIMS official lookup',publication='24 August 2026',freshness='snapshot',live=True,default_retrieval=True,direct_recommendation_allowed=False,universal_claim_allowed=False),
'laboratories/BIS_recognised_lab_Group_2.pdf':dict(id='bis_recognised_labs_group_2_2026_08_07',category='laboratories',family='laboratory_directory',scope='BIS laboratory facility snapshot',type='laboratory_snapshot',url='https://lims.bis.gov.in/home/labs/',authority='BIS LIMS official lookup',publication='7 August 2026',freshness='snapshot',live=True,default_retrieval=True,direct_recommendation_allowed=False,universal_claim_allowed=False),
'fees/BIS_Standard_certification_Fees.pdf':dict(id='bis_scheme_i_fees_snapshot_2026',category='fees',family='product_certification',scope='Scheme-I/product certification only',type='fee_snapshot',url='https://www.bis.gov.in/product-certification/product-certification-fee/?lang=en',authority='BIS official fee lookup',publication='2026 Gazette material',freshness='snapshot_as_of_official_page_2026_09_14',live=True,default_retrieval=True,direct_recommendation_allowed=False,universal_claim_allowed=False),
'helmet/PM_IS_4151_-Dec-24.pdf':dict(id='bis_pm_is_4151_dec_2024',category='helmet',family='helmet',scope='IS 4151:2015',type='product_manual',url='https://www.bis.gov.in/wp-content/uploads/2024/12/PM_IS_4151_-Dec-24.pdf',authority='BIS verified official',publication='December 2024',freshness='current_verified_download',live=False,default_retrieval=True,direct_recommendation_allowed=True,universal_claim_allowed=False)}
FMCS={'fmcs_application_form_v','fmcs_application_checklist'}
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def clean(t): return re.sub(r'\n{3,}','\n\n',re.sub(r'[ \t]+',' ',t.replace('\x00',''))).strip()
def safe_parts(text,limit=850):
 text=clean(text)
 if not text:return []
 return [text[i:i+limit].rsplit(' ',1)[0] if i+limit<len(text) else text[i:i+limit] for i in range(0,len(text),limit)]
def load_ocr():
 if not OCR.is_file(): raise ValueError('FMCS OCR chunks are required before V4 extraction')
 rows=[json.loads(line) for line in OCR.read_text(encoding='utf-8').splitlines() if line]
 if not rows or {x['metadata']['source_id'] for x in rows}!={*FMCS}: raise ValueError('both FMCS OCR sources must be present')
 for row in rows:
  validate_chunk(row); row['metadata']['default_retrieval']=True
 if len({x['id'] for x in rows})!=len(rows): raise ValueError('duplicate OCR chunk IDs')
 return rows
def main():
 OUT.mkdir(parents=True,exist_ok=True); ocr=load_ocr(); ocr_by_source={sid:[x for x in ocr if x['metadata']['source_id']==sid] for sid in FMCS}; pages=[]; chunks=[]; registry=[]
 for rel,meta in CANON.items():
  path=RAW/rel
  if not path.is_file(): raise ValueError(f'missing approved V4 source: {path}')
  reader=PdfReader(path); sha=digest(path); source={**meta,'source_id':meta['id'],'canonical_filename':path.name,'source_path':'data/raw/'+rel,'source_sha256':sha,'page_count':len(reader.pages),'status':'active','authority_status':'authoritative','language':'en','requires_live_verification':meta['live'],'live_verification_url':meta['url'] if meta['live'] else None,'extraction_status':'ocr' if meta['id'] in FMCS else 'embedded_text'}
  registry.append(source)
  for n,page in enumerate(reader.pages,1):
   text=clean(page.extract_text(extraction_mode='layout') or '')
   matching=[x['id'] for x in ocr_by_source.get(meta['id'],[]) if x['metadata']['page_start']==n]
   pages.append({'page_id':f"{meta['id']}:p{n}",'source_id':meta['id'],'source_filename':path.name,'page_number':n,'source_sha256':sha,'text':text,'chunk_ids':matching,'extraction_method':'ocr' if meta['id'] in FMCS else 'embedded_text'})
   if meta['id'] in FMCS: continue
   for ix,part in enumerate(safe_parts(text),1):
    noisy=part.lower().count('column ')>=4 or part.lower().count('left-to-right')>0 or part.count('-do-')>=3
    if noisy: continue
    cid=hashlib.sha256(f'{meta["id"]}:{n}:{ix}:{part}'.encode()).hexdigest()
    md={k:source[k] for k in ('source_id','canonical_filename','source_path','source_sha256','category','family','scope','type','url','authority','publication','freshness','requires_live_verification','live_verification_url','language','status','authority_status','default_retrieval','direct_recommendation_allowed','universal_claim_allowed')}
    md.update(source_filename=path.name,source_url=meta['url'],official_url=meta['url'],page_start=n,page_end=n,chunk_id=cid,chunk_type='section',scheme_scope=meta['scope'],retrieval_enabled=True,extraction_method='embedded_text',supporting_quote=part[:600])
    chunks.append({'id':cid,'document':'passage: '+part,'metadata':md}); pages[-1]['chunk_ids'].append(cid)
 chunks.extend(ocr)
 for row in chunks:
  if not isinstance(row['metadata'].get('default_retrieval'),bool): raise ValueError('V4 candidate chunk missing boolean default_retrieval')
 if len({x['id'] for x in chunks})!=len(chunks): raise ValueError('duplicate V4 addition IDs')
 for page in pages:
  if page['source_id'] in FMCS and not page['chunk_ids']: raise ValueError('FMCS page missing OCR chunks')
 for name,rows in [('pages',pages),('chunks',chunks)]: (OUT/(name+'.jsonl')).write_text(''.join(json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n' for x in rows),encoding='utf-8')
 (OUT/'source_registry.json').write_text(json.dumps(registry,indent=2,ensure_ascii=False,sort_keys=True)+'\n',encoding='utf-8')
 composition={'source_count':len(registry),'page_count':len(pages),'chunk_count':len(chunks),'per_source_pages':dict(Counter(x['source_id'] for x in pages)),'per_source_chunks':dict(Counter(x['metadata']['source_id'] for x in chunks)),'per_category_chunks':dict(Counter(x['metadata']['category'] for x in chunks)),'source_ids':sorted(x['source_id'] for x in registry)}
 (OUT/'v4_additions_composition_report.json').write_text(json.dumps(composition,indent=2,sort_keys=True)+'\n',encoding='utf-8'); (OUT/'summary.json').write_text(json.dumps(composition,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(json.dumps(composition,sort_keys=True))
if __name__=='__main__': main()
