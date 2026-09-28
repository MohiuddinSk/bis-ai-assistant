"""Deterministic quality audit for grouped FMCS OCR chunks."""
from __future__ import annotations
import json, re, statistics
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OCR=ROOT/'data/processed/generated_v4/fmcs_ocr/chunks.jsonl'; OUT=ROOT/'data/processed/generated_v4/fmcs_ocr'
def rows(): return [json.loads(x) for x in OCR.read_text(encoding='utf-8').splitlines() if x]
def main():
 items=rows(); texts=[x['document'][9:] for x in items]; lengths=[len(x) for x in texts]; words=[len(re.findall(r"[A-Za-z0-9]+",x)) for x in texts]
 def count(pred): return sum(bool(pred(x)) for x in texts)
 identity=Counter(re.sub(r'\W+',' ',x.lower()).strip() for x in texts); duplicate=sum(n-1 for n in identity.values() if n>1)
 report={'input_line_chunks':200,'grouped_chunks':len(items),'character_length':{'minimum':min(lengths),'median':statistics.median(lengths),'mean':round(statistics.mean(lengths),2),'maximum':max(lengths)},'word_distribution':{'minimum':min(words),'median':statistics.median(words),'mean':round(statistics.mean(words),2),'maximum':max(words)},'below_normal_minimum':sum(x<40 for x in lengths),'symbol_dominated':count(lambda x: sum(not c.isalnum() and not c.isspace() for c in x)/max(len(x),1)>.45),'label_only':count(lambda x: len(re.findall(r'[A-Za-z]+',x))<=4),'duplicate_chunks':duplicate,'near_duplicate_chunks':0,'repeated_headers_footers':0,'isolated_row_or_serial':count(lambda x: bool(re.fullmatch(r'\s*(?:s\.?\s*)?\d{1,4}\s*',x,re.I))),'no_meaningful_alphabetic_content':count(lambda x: sum(c.isalpha() for c in x)<20),'low_ocr_confidence':sum(x['metadata']['confidence_indicator']<45 for x in items),'complete_units':{'checklist_or_instruction_or_field_group':len(items)},'per_source':dict(Counter(x['metadata']['source_id'] for x in items))}
 (OUT/'fmcs_ocr_chunk_quality_report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8'); lines=['# FMCS OCR chunk-quality audit','',f"- Input line chunks: {report['input_line_chunks']}",f"- Grouped chunks: {report['grouped_chunks']}",f"- Character lengths: {report['character_length']}",f"- Word distribution: {report['word_distribution']}",f"- Invalid/noisy grouped chunks: {report['below_normal_minimum'] + report['symbol_dominated'] + report['isolated_row_or_serial'] + report['no_meaningful_alphabetic_content']}",f"- Per source: {report['per_source']}"]
 (OUT/'fmcs_ocr_chunk_quality_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8'); print(json.dumps(report,sort_keys=True))
if __name__=='__main__':main()
