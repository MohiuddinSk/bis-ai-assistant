"""Explicit V3/V4 runtime selection contracts; no index writes."""
import os
import unittest
from unittest.mock import patch

from backend.settings import get_retrieval_settings


class PromotionRuntimeConfigurationTests(unittest.TestCase):
    def test_v3_defaults_are_explicit_and_rollback_ready(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = get_retrieval_settings()
        self.assertEqual(settings.data_path, 'data/processed/generated_v3')
        self.assertEqual(settings.persist_path, 'data/chroma')
        self.assertEqual(settings.collection_name, 'bis_toys_v3_e73aab14a72f7908_39b347ab687e')

    def test_v4_selection_is_versioned_not_latest_directory(self):
        with patch.dict(os.environ, {'RETRIEVAL_CORPUS_VERSION':'v4_01346f7d11f1'}, clear=True):
            settings = get_retrieval_settings()
        self.assertEqual(settings.data_path, 'data/processed/generated_v4')
        self.assertEqual(settings.persist_path, 'data/chroma_v4_01346f7d11f1')
        self.assertEqual(settings.collection_name, 'bis_corpus_v4_candidate_01346f7d11f1')

    def test_unknown_version_is_rejected(self):
        with patch.dict(os.environ, {'RETRIEVAL_CORPUS_VERSION':'latest'}, clear=True), self.assertRaises(ValueError):
            get_retrieval_settings()

    def test_incoming_path_cannot_be_selected_by_a_version_default(self):
        with patch.dict(os.environ, {'RETRIEVAL_CORPUS_VERSION':'v4_01346f7d11f1'}, clear=True):
            self.assertNotIn('incoming', get_retrieval_settings().data_path)
