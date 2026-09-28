"""Read-only validation of the isolated hash-named candidate collection."""
from __future__ import annotations
import argparse, json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data/processed/generated_v4'; CANDIDATE=ROOT/'data/chroma_v4_candidate'
def main(argv=None):
 parser=argparse.ArgumentParser(); parser.add_argument('--persist-path',type=Path,required=True); parser.add_argument('--collection',required=True); args=parser.parse_args(argv)
 import chromadb
 from chromadb.config import Settings
 records=[json.loads(x) for x in (DATA/'chunks_complete.jsonl').read_text(encoding='utf-8').splitlines() if x]; expected={x['id'] for x in records}
 client=chromadb.PersistentClient(path=str(args.persist_path),settings=Settings(anonymized_telemetry=False)); collection=client.get_collection(args.collection,embedding_function=None); result=collection.get(include=['metadatas']); ids=set(result['ids'])
 if len(records)!=len(expected) or ids!=expected or collection.count()!=len(records): raise ValueError('candidate membership mismatch')
 per_source=Counter(x['source_id'] for x in result['metadatas']); per_category=Counter(x.get('category','v3_toys') for x in result['metadatas'])
 v4=[x for x in result['metadatas'] if x.get('source_id','').startswith('bis_') or x.get('category') in {'fmcs','fees','jewellery','helmet','laboratories'}]; report={'collection_name':collection.name,'persist_path':str(args.persist_path).replace('\\','/'),'jsonl_count':len(records),'unique_jsonl_ids':len(expected),'chroma_count':collection.count(),'unique_chroma_ids':len(ids),'source_ids':sorted(per_source),'represented_source_count':len(per_source),'per_source_membership':dict(sorted(per_source.items())),'per_category_membership':dict(sorted(per_category.items())),'metadata_complete':all(bool(x.get('source_id')) and bool(x.get('source_filename')) and x.get('page_start') for x in result['metadatas']),'v4_default_retrieval_all_true':all(x.get('default_retrieval') is True for x in v4),'production_path_selected':False}
 (DATA/'staging_index_validation_report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(json.dumps(report,sort_keys=True))
if __name__=='__main__':main()
