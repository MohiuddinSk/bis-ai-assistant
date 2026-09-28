"""Write the canonical deterministic V4 embedding manifest; never indexes data."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data/processed/generated_v4'
sys.path.insert(0,str(ROOT))
def main():
 from retrieval.embeddings import MODEL,REVISION
 raw=(DATA/'chunks_complete.jsonl').read_bytes(); identity=hashlib.sha256(raw).hexdigest()
 report={'schema_version':'v4_embedding_manifest/1','model':MODEL,'model_revision':REVISION,'dimension':384,'normalize_embeddings':True,'distance':'cosine','query_prefix':'query: ','passage_prefix':'passage: ','corpus_sha256':identity,'chunk_count':len(raw.splitlines()),'source_artifact':'chunks_complete.jsonl'}
 (DATA/'embedding_manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n'); print(json.dumps(report,sort_keys=True))
if __name__=='__main__':main()
