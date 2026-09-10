import unittest
from unittest.mock import patch
from ingestion.extract_and_chunk import clean_text, split_text
from retrieval.embeddings import encode

class FakeVectors:
    def tolist(self): return [[1.0,0.0]]
class FakeTokenizer:
    def encode(self,text): return text.split()
class FakeEncoder:
    tokenizer=FakeTokenizer()
    def encode(self,texts,**kwargs):
        self.texts=texts; self.kwargs=kwargs
        return FakeVectors()

class DataContractTests(unittest.TestCase):
    def test_body_lines_are_never_removed_by_frequency(self):
        text='Header\nMust retain this requirement\nMust retain this requirement\nFooter'
        self.assertEqual(clean_text(text),text)
    def test_split_preserves_words_and_order(self):
        text=('Requirement Hindi हिंदी and clauses 4.29 apply. '*100)+'\nTable | value | unit'
        chunks=split_text(text)
        self.assertEqual(' '.join(' '.join(chunks).split()),' '.join(text.split()))
        self.assertTrue(all(len(c)<=900 for c in chunks))
    def test_shared_query_and_passage_contract(self):
        fake=FakeEncoder()
        with patch('retrieval.embeddings.model',return_value=fake):
            encode(['नमस्ते'],'query')
            self.assertEqual(fake.texts,['query: नमस्ते'])
            self.assertTrue(fake.kwargs['normalize_embeddings'])
            encode(['passage: text'],'passage')
            self.assertEqual(fake.texts,['passage: text'])
    def test_no_silent_truncation(self):
        with patch('retrieval.embeddings.model',return_value=FakeEncoder()):
            with self.assertRaises(ValueError): encode(['word '*513],'passage')
    def test_invalid_prefix_rejected(self):
        with self.assertRaises(ValueError): encode(['text'],'other')
if __name__=='__main__': unittest.main()
