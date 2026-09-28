"""Strict embedding package contract tests; no collection or file mutation."""
import copy
import hashlib
import json
import unittest
from pathlib import Path

from retrieval.embeddings import MODEL, REVISION
from retrieval.search import validate_embedding_manifest

ROOT = Path(__file__).resolve().parents[1]


class EmbeddingManifestContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v3 = json.loads((ROOT / 'data/processed/generated_v3/embedding_manifest.json').read_text())
        cls.v4 = json.loads((ROOT / 'data/processed/generated_v4/embedding_manifest.json').read_text())

    def test_strict_v3_and_canonical_v4_are_accepted(self):
        self.assertEqual(validate_embedding_manifest(self.v3), 'v3')
        self.assertEqual(validate_embedding_manifest(self.v4), 'v4')

    def test_missing_model_or_revision_is_rejected(self):
        for key in ('model', 'model_revision'):
            bad = copy.deepcopy(self.v4); bad.pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_embedding_manifest(bad)

    def test_wrong_model_or_revision_is_rejected(self):
        for key, value in (('model', 'other/model'), ('model_revision', 'wrong')):
            bad = copy.deepcopy(self.v4); bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_embedding_manifest(bad)

    def test_v4_schema_and_static_contract_are_strict(self):
        for key, value in (('schema_version', 'v4_embedding_manifest/999'), ('dimension', 768),
                           ('distance', 'l2'), ('query_prefix', ''), ('passage_prefix', 'query: ')):
            bad = copy.deepcopy(self.v4); bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_embedding_manifest(bad)

    def test_validation_report_shape_cannot_masquerade_as_manifest(self):
        with self.assertRaises(ValueError):
            validate_embedding_manifest({'records': 1160, 'eligible': 1084, 'passed': True})

    def test_v4_hash_and_count_match_the_artifact(self):
        raw = (ROOT / 'data/processed/generated_v4/chunks_complete.jsonl').read_bytes()
        self.assertEqual(self.v4['corpus_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.v4['chunk_count'], len(raw.splitlines()))

    def test_v3_contract_values_remain_unchanged(self):
        self.assertEqual((self.v3['model'], self.v3['model_revision']), (MODEL, REVISION))
