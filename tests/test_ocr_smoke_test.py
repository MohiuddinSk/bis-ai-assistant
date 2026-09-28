import unittest
from ingestion.ocr_smoke_test import EXPECTED
class OcrSmokeContractTests(unittest.TestCase):
 def test_expected_phrase_is_stable(self): self.assertEqual(EXPECTED,'BIS SAARTHI OCR TEST 4151')
