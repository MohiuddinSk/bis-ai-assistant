"""Build a fresh hash-named V4 candidate collection; production Chroma is refused."""
from __future__ import annotations
import argparse, hashlib, json, sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); DATA=ROOT/'data/processed/generated_v4'; DEFAULT=ROOT/'data/chroma_v4_candidate'
from retrieval.embeddings import encode, MODEL, REVISION
def rows(path): return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x]
def main(argv=None):
 parser=argparse.ArgumentParser(); parser.add_argument('--persist-path',type=Path,default=DEFAULT); args=parser.parse_args(argv)
 persist=args.persist_path.resolve()
 if not persist.name.startswith('chroma_v4_candidate_') or persist== (ROOT/'data/chroma').resolve(): raise ValueError('new hash-named candidate path only; production path refused')
 chunk_file=DATA/'chunks_complete.jsonl'; records=rows(chunk_file); ids=[x['id'] for x in records]
 if len(ids)!=len(set(ids)): raise ValueError('duplicate JSONL IDs')
 artifact_hash=hashlib.sha256(chunk_file.read_bytes()).hexdigest(); name='bis_corpus_v4_candidate_'+artifact_hash[:12]
 import chromadb
 from chromadb.config import Settings
 client=chromadb.PersistentClient(path=str(persist),settings=Settings(anonymized_telemetry=False)); collection=client.get_or_create_collection(name,embedding_function=None,metadata={'hnsw:space':'cosine','dataset':'v4_candidate','artifact_sha256':artifact_hash,'model':MODEL,'model_revision':REVISION})
 if collection.metadata.get('dataset')!='v4_candidate' or collection.metadata.get('artifact_sha256')!=artifact_hash: raise ValueError('candidate collection metadata mismatch')
 for start in range(0,len(records),32):
  batch=records[start:start+32]; metadata=[]
  for item in batch:
   row={k:v for k,v in item['metadata'].items() if v is not None}
   if not all(isinstance(v,(str,int,float,bool)) for v in row.values()): raise ValueError('non-scalar Chroma metadata')
   metadata.append(row)
  collection.upsert(ids=[x['id'] for x in batch],documents=[x['document'] for x in batch],metadatas=metadata,embeddings=encode([x['document'] for x in batch],'passage'))
 actual=collection.get(include=['metadatas']); actual_ids=set(actual['ids'])
 if actual_ids!=set(ids) or collection.count()!=len(ids): raise ValueError('candidate membership mismatch or stale records')
 source_counts=Counter(row['source_id'] for row in actual['metadatas']); category_counts=Counter(row.get('category','v3_toys') for row in actual['metadatas'])
 report={'persist_path':'data/chroma_v4_candidate','collection_name':name,'artifact_sha256':artifact_hash,'jsonl_count':len(records),'unique_jsonl_ids':len(set(ids)),'chroma_count':collection.count(),'unique_chroma_ids':len(actual_ids),'source_ids':sorted(source_counts),'per_source_membership':dict(sorted(source_counts.items())),'per_category_membership':dict(sorted(category_counts.items())),'metadata_complete':True,'production_path_refused':True}
 (DATA/'staging_index_validation_report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8'); (DATA/'embedding_manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(json.dumps(report,sort_keys=True))
if __name__=='__main__':main()
