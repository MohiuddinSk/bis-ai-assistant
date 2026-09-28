"""Pure, deterministic checks for the shared hybrid policy helpers."""
import unittest

from retrieval.hybrid_rerank import intents, rerank


def row(chunk_id, category, text, distance=.25, **metadata):
    return {'id': chunk_id, 'document': text,
            'metadata': {'category': category, **metadata}, 'distance': distance}


class HybridIntentTests(unittest.TestCase):
    def test_categories_cover_supported_languages(self):
        cases = {
            'fees': ['fee snapshot', 'बीआईएस शुल्क', 'प्रमाणन शुल्क', 'சான்றிதழ் கட்டண', 'BIS ফি'],
            'laboratories': ['BIS laboratory', 'प्रयोगशाला', 'चाचणी', 'ஆய்வக', 'পরীক্ষাগার'],
            'fmcs': ['FMCS Form V', 'फॉर्म', 'फॉर्म', 'படிவ', 'ফর্ম'],
            'jewellery': ['jeweller hallmark', 'जौहरी', 'दागिने', 'நகை', 'গয়না'],
            'helmet': ['IS 4151 helmet', 'हेलमेट', 'शिरस्त्राण', 'ஹெல்மெட்', 'হেলমেট'],
            'toys': ['battery toy', 'खिलौना', 'खेळणी', 'பொம்மை', 'খেলনা'],
        }
        for category, queries in cases.items():
            for query in queries:
                with self.subTest(category=category, query=query):
                    self.assertIn(category, intents(query))

    def test_generic_and_vague_queries_do_not_force_category(self):
        self.assertEqual(intents('BIS certification process'), [])
        self.assertEqual(intents('What applies to my product?'), [])

    def test_mixed_categories_are_detected_without_source_selection(self):
        self.assertEqual(set(intents('FMCS Form V and helmet IS 4151 fee')),
                         {'fmcs', 'helmet', 'fees'})


class RerankTests(unittest.TestCase):
    def test_category_and_identifier_rank_deterministically(self):
        rows = [row('other', 'jewellery', 'BIS guidance', .05),
                row('helmet', 'helmet', 'IS 4151 helmet manual', .25)]
        first = rerank('IS 4151 helmet manual', rows)
        second = rerank('IS 4151 helmet manual', rows)
        self.assertEqual([x['id'] for x in first], ['helmet', 'other'])
        self.assertEqual([x['id'] for x in first], [x['id'] for x in second])

    def test_generic_tokens_do_not_overpower_domain_evidence(self):
        rows = [row('fee', 'fees', 'Scheme I certification fee and charges', .30),
                row('generic', 'jewellery', 'BIS product certification document', .05)]
        self.assertEqual(rerank('BIS certification fee', rows)[0]['id'], 'fee')

    def test_metadata_is_preserved(self):
        original = row('lab', 'laboratories', 'laboratory scope', .2,
                       requires_live_verification=True)
        self.assertIs(rerank('laboratory', [original])[0]['metadata'], original['metadata'])
