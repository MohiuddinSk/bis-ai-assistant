"""Rebuild a traceable, page-aware dataset without altering source PDFs."""
from __future__ import annotations
import hashlib
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote
import fitz
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrieval.embeddings import MODEL, REVISION
OUT = ROOT / 'data/processed/generated_v3'
RAW = ROOT / 'data/raw'
PIPELINE = '3.0.2'
KINDS = {'product_manual_2026.pdf': 'manual', 'Toy_QC_order.pdf': 'qco',
 'toys-faqs.pdf': 'faq', '10-steps-for-BIS-toy-certification.pdf': 'guidance',
 'Notification-of-Transition-Facilitation-Quality-Control-Order-2026.pdf': 'transition_order'}
def sha(value):
    return hashlib.sha256(value).hexdigest()
def norm(text):
    return re.sub(r'\s+', ' ', text).strip()
def clean_text(text):
    # No frequency-based deletion: repeated text may be legally meaningful.
    return '\n'.join(line.rstrip() for line in text.replace('\x00', '').splitlines()).strip()
def split_text(text, budget=900):
    # Preserve line/table boundaries; split overlong lines at whitespace only.
    units = []
    for line in text.splitlines():
        if len(line) <= budget:
            units.append(line)
            continue
        current = ''
        for word in line.split():
            if current and len(current) + len(word) + 1 > budget:
                units.append(current)
                current = ''
            current = (current + ' ' + word).strip()
        if current:
            units.append(current)
    result, current = [], ''
    for unit in units:
        if current and len(current) + len(unit) + 1 > budget:
            result.append(current)
            current = ''
        current = (current + '\n' + unit).strip()
    if current:
        result.append(current)
    return result

def main():
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
    paths = sorted(RAW.glob('*.pdf'))
    if not paths:
        raise ValueError('No raw PDFs')
    inventory = {p.name: sha(p.read_bytes()) for p in paths}
    version = sha(json.dumps({'sources': inventory, 'pipeline': PIPELINE, 'model_revision': REVISION}, sort_keys=True).encode())[:16]
    pages, sources, chunks, duplicates = [], [], [], []
    seen_files, seen_text = {}, {}
    def token_split(text):
        if len(tokenizer.encode('passage: ' + text)) <= 480:
            return [text]
        spaces = [m.start() for m in re.finditer(r'\s+', text)]
        if not spaces:
            raise ValueError('Unbroken text exceeds token limit; needs review')
        cut = min(spaces, key=lambda x: abs(x - len(text)//2))
        return token_split(text[:cut].strip()) + token_split(text[cut:].strip())
    for path in paths:
        sid = re.sub(r'[^A-Za-z0-9]+', '_', path.stem)
        source_hash = inventory[path.name]
        kind = KINDS.get(path.name, 'amendment' if path.name in {
            'Toys-QCO-2024.pdf', 'Toys-Extension.pdf', 'Toys-Quality-Control-Second-Amendment-Order-2020.pdf'} else 'unknown')
        reader = PdfReader(path)
        pdf = fitz.open(path)
        url = 'https://github.com/MohiuddinSk/bis-ai-assistant/blob/ba16e5351e9229626997761038064e37615eecc9/data/raw/' + quote(path.name)
        # URL is a repository locator, not an assertion of official provenance.
        original = ROOT / 'data/processed/generated_v2/source_registry.json'
        prior = json.loads(original.read_text(encoding='utf-8')) if original.exists() else []
        if not any(s['source_filename'] == path.name and s['source_sha256'] == source_hash for s in prior):
            url = ''
        source = {'source_id': sid, 'source_filename': path.name, 'source_path': 'data/raw/' + path.name,
            'source_sha256': source_hash, 'page_count': len(pdf), 'source_type': kind,
            'source_url': url, 'official_url': '', 'authority_status': 'unverified',
            'document_revision': '', 'publication_date': '', 'date_precision': 'unknown',
            'dataset_version': version, 'canonical_source_id': seen_files.get(source_hash, sid)}
        if source_hash in seen_files:
            duplicates.append({'type': 'exact_file', 'source_id': sid, 'canonical_source_id': seen_files[source_hash]})
        else:
            seen_files[source_hash] = sid
        for index, fp in enumerate(pdf):
            errors = []
            try:
                primary = reader.pages[index].extract_text(extraction_mode='layout') or ''
            except Exception as exc:
                primary = ''; errors.append(type(exc).__name__)
            alternate = fp.get_text('text', sort=True) or ''
            raw = primary if len(norm(primary)) >= len(norm(alternate)) * .7 else alternate
            method = 'pypdf_layout' if raw == primary else 'pymupdf'
            text = clean_text(raw)
            page_number = index + 1
            reviewed_form = path.name == 'product_manual_2026.pdf' and page_number in (57,61) and source_hash == next((s['source_sha256'] for s in prior if s['source_filename']==path.name), None)
            status = 'reviewed_blank_form' if reviewed_form else 'needs_review' if len(norm(text)) < 80 else 'extracted'
            page = {'source_id': sid, 'source_filename': path.name, 'page_number': page_number,
                'source_sha256': source_hash, 'raw_text': raw, 'clean_text': text,
                'extractor': method, 'extraction_errors': errors, 'review_status': status,
                'table_count': 0, 'chunk_ids': []}
            if index == 0 and kind == 'manual':
                match = re.search(r'PM/\s*9873/\s*(\d+)\s+(\w+)\s+(20\d\d)', norm(text))
                if match:
                    source.update(document_revision='PM/9873/' + match[1], publication_date=match[2]+' '+match[3], date_precision='month')
            payloads = [('document_text', part) for part in split_text(text)]
            try:
                tables = fp.find_tables().tables
                page['table_count'] = len(tables)
                for table_index, table in enumerate(tables):
                    rows = table.extract()
                    if not rows: continue
                    for row_index, row in enumerate(rows, 1):
                        line = ' | '.join(f'Column {n}: '+norm(str(c or '')) for n,c in enumerate(row,1))
                        if any(norm(str(c or '')) for c in row):
                            payloads.append(('table_row', f'Table {table_index+1}; row {row_index} (left-to-right cells; check PDF headers and ditto references)\n{line}'))
            except Exception as exc:
                page['extraction_errors'].append('table:' + type(exc).__name__)
            for chunk_type, payload in payloads:
                for part in token_split(payload):
                    document = 'passage: ' + part
                    cid = sha((version + sid + str(page_number) + chunk_type + document).encode())
                    if cid in page['chunk_ids']: continue
                    page['chunk_ids'].append(cid)
                    fingerprint = sha(document.encode())
                    enabled = status != 'needs_review' and kind != 'unknown' and source['canonical_source_id'] == sid
                    meta = {k: source[k] for k in ('source_id','source_filename','source_path','source_sha256','source_type','source_url','dataset_version')}
                    meta.update(page_start=page_number, page_end=page_number, chunk_type=chunk_type,
                        table_context_status='check_pdf_headers_and_ditto' if chunk_type=='table_row' else 'not_applicable',
                        document_revision=source['document_revision'], publication_date=source['publication_date'],
                        authority_status='unverified', source_status='uploaded_source_not_verified_current',
                        review_status=status, retrieval_enabled=enabled,
                        default_retrieval=enabled and kind not in ('faq','guidance'),
                        language='mixed' if re.search(r'[\u0900-\u097f]', part) else 'en',
                        section=next((norm(line) for line in part.splitlines() if re.match(r'^(ANNEX|APPENDIX)\b', line.strip())), ''),
                        clause=next((m.group(1) for line in part.splitlines() if (m := re.match(r'^\s*(\d+\.\d+(?:\.\d+)*)\s', line))), ''),
                        structural_labels_status='literal_local_labels_only',
                        char_count=len(document), token_count=len(tokenizer.encode(document)), text_sha256=fingerprint)
                    chunks.append({'id': cid, 'document': document, 'metadata': meta})
                    if fingerprint in seen_text:
                        duplicates.append({'type':'exact_chunk_text', 'chunk_id':cid,'canonical_chunk_id':seen_text[fingerprint], 'action':'retained_for_page_provenance'})
                    else: seen_text[fingerprint] = cid
            pages.append(page)
        pdf.close()
        source_text = norm(' '.join(p['raw_text'] for p in pages if p['source_id']==sid))
        if not source['publication_date']:
            match = re.search(r'New Delhi,?\s+the\s+(\d+(?:st|nd|rd|th)?\s+\w+,?\s+20\d\d)',source_text)
            if match:
                source.update(publication_date=match[1],date_precision='day')
        source['cited_notifications'] = sorted(set(re.findall(r'S\.\s*O\.\s*\d+\s*\(E\)',source_text)))
        for chunk in chunks:
            if chunk['metadata']['source_id']==sid:
                chunk['metadata']['publication_date']=source['publication_date']
                chunk['metadata']['document_revision']=source['document_revision']
        sources.append(source)
    for i, left in enumerate(sources):
        a = norm(' '.join(p['clean_text'] for p in pages if p['source_id']==left['source_id']))
        for right in sources[i+1:]:
            b = norm(' '.join(p['clean_text'] for p in pages if p['source_id']==right['source_id']))
            if a and b and min(len(a),len(b))/max(len(a),len(b)) >= .9:
                similarity = SequenceMatcher(None,a,b).ratio()
                if similarity >= .95 and left['source_sha256'] != right['source_sha256']:
                    duplicates.append({'type':'near_document_text','source_id':right['source_id'],
                        'candidate_source_id':left['source_id'],'similarity':round(similarity,4),'action':'retained_pending_review'})
    OUT.mkdir(parents=True, exist_ok=True)
    for name, records in [('pages',pages), ('chunks',chunks)]:
        (OUT / (name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    manifest = {'dataset_version': version, 'pipeline_version': PIPELINE, 'model': MODEL, 'model_revision': REVISION,
        'dimension':384, 'normalize_embeddings': True, 'distance':'cosine', 'query_prefix':'query: ', 'passage_prefix':'passage: ',
        'max_tokens':480, 'collection_name':'bis_toys_v3_'+version+'_'+sha((OUT/'chunks.jsonl').read_bytes())[:12], 'chunks_sha256':sha((OUT/'chunks.jsonl').read_bytes()),
        'retrieval_chunk_count':sum(c['metadata']['retrieval_enabled'] for c in chunks)}
    for name, value in [('source_registry',sources),('duplicate_map',duplicates),('embedding_manifest',manifest),
            ('summary',{'pdf_count':len(sources),'page_count':len(pages),'chunk_count':len(chunks),
                'review_pages':[{'source':p['source_filename'],'page':p['page_number'],'status':p['review_status']} for p in pages if p['review_status']!='extracted'],
                'chunks_by_source':dict(Counter(c['metadata']['source_filename'] for c in chunks))})]:
        (OUT/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print((OUT/'summary.json').read_text(encoding='utf-8'))
if __name__ == '__main__': main()
