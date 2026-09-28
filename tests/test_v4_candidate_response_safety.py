"""Candidate-backed ChatService safety gate; no provider or index writes."""
import unittest
from evaluation.evaluate_v4_candidate_response_safety import evaluate


class CandidateResponseSafetyTests(unittest.TestCase):
    def test_provider_disabled_candidate_safety_matrix(self):
        report = evaluate()
        self.assertEqual(report['passed'], report['total'], report['failed'])
        self.assertTrue(all(not row['historical_source'] for row in report['results']))
        self.assertTrue(all(not row['secret_or_injection_leak'] for row in report['results']))
