"""Mocked public-search contract checks: no Chroma persistence writes."""
import unittest
from unittest.mock import patch

from retrieval.search import Retriever


class FakeCollection:
    def __init__(self, fail_category=False, empty_category=False):
        self.calls = []; self.fail_category = fail_category; self.empty_category = empty_category
    def count(self): return 100
    def query(self, **kwargs):
        self.calls.append(kwargs)
        if '$and' in kwargs['where']:
            if self.fail_category: raise RuntimeError('category unavailable')
            if self.empty_category: return {'ids':[[]], 'documents':[[]], 'metadatas':[[]], 'distances':[[]]}
            return {'ids': [['fee']], 'documents': [['Scheme I fee charges']],
                    'metadatas': [[{'category':'fees','source_id':'fees'}]], 'distances': [[.25]]}
        return {'ids': [['generic', 'fee']], 'documents': [['BIS certification document', 'Scheme I fee charges']],
                'metadatas': [[{'category':'jewellery','source_id':'j'}, {'category':'fees','source_id':'fees'}]],
                'distances': [[.1, .25]]}


class RetrieverSearchContractTests(unittest.TestCase):
    def make(self, **kwargs):
        retriever = Retriever.__new__(Retriever); retriever.collection = FakeCollection(**kwargs)
        return retriever

    @patch('retrieval.search.encode', return_value=[[0.0]])
    def test_global_and_category_queries_combine_filters(self, _encode):
        r = self.make(); result = r.search('BIS fee charges', k=1)
        self.assertEqual(result['ids'][0], ['fee'])
        self.assertEqual(r.collection.calls[0]['where'], {'default_retrieval': True})
        self.assertEqual(r.collection.calls[1]['where'], {'$and': [{'default_retrieval': True}, {'category': 'fees'}]})

    @patch('retrieval.search.encode', return_value=[[0.0]])
    def test_vague_query_runs_only_global_retrieval(self, _encode):
        r = self.make(); r.search('What applies to my product?', k=2)
        self.assertEqual(len(r.collection.calls), 1)

    @patch('retrieval.search.encode', return_value=[[0.0]])
    def test_empty_or_failed_category_query_keeps_global_results(self, _encode):
        for kwargs in ({'empty_category': True}, {'fail_category': True}):
            with self.subTest(kwargs=kwargs):
                result = self.make(**kwargs).search('BIS fee charges', k=2)
                self.assertEqual(result['ids'][0], ['fee', 'generic'])

    @patch('retrieval.search.encode', return_value=[[0.0]])
    def test_duplicate_ids_merge_and_return_schema_stays_chroma_shaped(self, _encode):
        result = self.make().search('BIS fee charges', k=5)
        self.assertEqual(result['ids'][0].count('fee'), 1)
        self.assertEqual(set(result), {'ids','documents','metadatas','distances'})

    @patch('retrieval.search.encode', return_value=[[0.0]])
    def test_existing_guidance_filter_is_preserved(self, _encode):
        r = self.make(); r.search('BIS fee charges', k=1, include_guidance=True)
        self.assertEqual(r.collection.calls[0]['where'], {'retrieval_enabled': True})
        self.assertEqual(r.collection.calls[1]['where'], {'$and': [{'retrieval_enabled': True}, {'category': 'fees'}]})
