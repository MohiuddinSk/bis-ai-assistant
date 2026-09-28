import json, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data/processed/generated_v4'
class CorpusV4ContractTests(unittest.TestCase):
 def test_registry_is_approved_only_and_metadata_complete(self):
  rows=json.loads((DATA/'source_registry.json').read_text())
  self.assertEqual(len(rows),7)
  for row in rows:self.assertTrue(all(row.get(k) is not None for k in ('id','canonical_filename','source_sha256','category','scope','url','authority','freshness')))
  self.assertTrue(all('2019 helmet' not in row['source_path'] for row in rows))
 def test_fmcs_scope_and_live_snapshot_warnings(self):
  rows=json.loads((DATA/'source_registry.json').read_text())
  fmcs=[x for x in rows if x['category']=='fmcs']; self.assertEqual(len(fmcs),2); self.assertTrue(all(x['scope']=='FMCS only' for x in fmcs))
  snaps=[x for x in rows if x['requires_live_verification']]; self.assertEqual({x['category'] for x in snaps},{'laboratories','fees'}); self.assertTrue(all(x['live_verification_url'] for x in snaps))
 def test_chunks_have_page_scope_and_no_serialized_table_noise(self):
  chunks=[json.loads(x) for x in (DATA/'chunks.jsonl').read_text().splitlines()]
  self.assertTrue(chunks); self.assertTrue(all(x['metadata']['page_start']>0 and x['metadata']['scheme_scope'] for x in chunks))
  self.assertFalse(any(x['document'].lower().count('column ')>=4 or x['document'].count('-do-')>=3 for x in chunks))
if __name__=='__main__':unittest.main()
