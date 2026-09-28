"""The evaluator's wrapper must return production Retriever.search ordering exactly."""
import unittest
from pathlib import Path

from evaluation.evaluate_v4_retrieval import retrieve
from retrieval.search import Retriever

ROOT = Path(__file__).resolve().parents[1]


class EvaluatorProductionEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retriever = Retriever(
            data_path=ROOT / 'data/processed/generated_v4',
            persist_path=ROOT / 'data/chroma_v4_candidate_01346f7d11f1',
            collection_name='bis_corpus_v4_candidate_01346f7d11f1',
        )

    def test_wrapper_preserves_production_order(self):
        for query in ('BIS product certification fee snapshot as of date', 'BIS সার্টিফিকেশন ফি স্ন্যাপশট',
                      'Which standard applies to a battery-operated toy?', 'What is Form V used for in FMCS?',
                      'Current product manual for IS 4151 helmet', 'What applies to my product?'):
            with self.subTest(query=query):
                direct = self.retriever.search(query, k=10)['ids'][0]
                self.assertEqual(retrieve(self.retriever, query, k=10)['ids'][0], direct)
