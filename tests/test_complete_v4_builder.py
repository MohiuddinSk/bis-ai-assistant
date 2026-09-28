import json, unittest
from pathlib import Path
from ingestion.fmcs_ocr_chunks import validate_chunk

ROOT=Path(__file__).resolve().parents[1]; V3=ROOT/'data/processed/generated_v3'; V4=ROOT/'data/processed/generated_v4'
def rows(path): return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x]
class CompleteV4BuilderTests(unittest.TestCase):
 def test_complete_membership_preserves_v3_and_adds_seven_sources(self):
  complete=rows(V4/'chunks_complete.jsonl'); v3=rows(V3/'chunks.jsonl'); sources={x['metadata']['source_id'] for x in complete}
  self.assertEqual(len(sources),15); self.assertTrue({x['id'] for x in v3}<={x['id'] for x in complete}); self.assertEqual(len({x['id'] for x in complete}),len(complete))
  self.assertTrue({'fmcs_application_form_v','fmcs_application_checklist'}<=sources)
  self.assertFalse({'Safety_of_toys','IS_4151_2019','Revised_Guidelines_for_JEWELLERS_Jan_24'}&sources)
 def test_ocr_additions_are_valid_and_separate(self):
  additions=rows(V4/'chunks.jsonl'); fmcs=[x for x in additions if x['metadata']['source_id'].startswith('fmcs_')]
  self.assertEqual({x['metadata']['source_id'] for x in fmcs},{'fmcs_application_form_v','fmcs_application_checklist'})
  for row in fmcs: validate_chunk(row)
 def test_candidate_path_guard(self):
  from ingestion.build_chroma_v4 import DEFAULT
  self.assertEqual(DEFAULT.name,'chroma_v4_candidate')
if __name__=='__main__':unittest.main()
