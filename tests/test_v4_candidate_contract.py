import json, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; REPORT=ROOT/'data/processed/generated_v4/staging_index_validation_report.json'
class CandidateIndexTests(unittest.TestCase):
 def test_candidate_counts_and_source_membership_match(self):
  report=json.loads(REPORT.read_text())
  self.assertEqual(report['jsonl_count'],report['unique_jsonl_ids']); self.assertEqual(report['jsonl_count'],report['chroma_count']); self.assertEqual(report['chroma_count'],report['unique_chroma_ids'])
  self.assertEqual(report['represented_source_count'],15); self.assertTrue({'fmcs_application_form_v','fmcs_application_checklist'}<=set(report['source_ids'])); self.assertFalse(report['production_path_selected'])
if __name__=='__main__':unittest.main()
