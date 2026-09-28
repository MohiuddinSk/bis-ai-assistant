"""Read-only deterministic audit for an incoming PDF/DOCX corpus."""
from __future__ import annotations
import argparse, hashlib, json, re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIME = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def normalized_category(path: Path, root: Path) -> str:
    parts = path.relative_to(root).parts
    value = parts[1] if len(parts) > 1 and parts[0].casefold() == "categories" else (parts[0] if parts else "uncategorized")
    return {"jwellery": "jewellery"}.get(value.casefold(), value.casefold())

def extract_preview(path: Path) -> tuple[str, str]:
    try:
        if path.suffix.casefold() == ".pdf":
            from pypdf import PdfReader
            text = PdfReader(path).pages[0].extract_text() or ""
        else:
            from docx import Document
            text = "\n".join(p.text for p in Document(path).paragraphs[:40])
        text = " ".join(text.split())[:4000]
        return text[:240], ""
    except Exception as exc:
        return "", type(exc).__name__

def audit(incoming: Path, raw: Path, registry: Path) -> list[dict]:
    raw_hashes = {sha256(path): str(path.relative_to(ROOT)) for path in raw.rglob("*") if path.suffix.casefold() in MIME}
    registry_hashes = {item.get("source_sha256"): item.get("source_filename") for item in json.loads(registry.read_text(encoding="utf-8"))}
    files = sorted(path for path in incoming.rglob("*") if path.is_file() and path.suffix.casefold() in MIME)
    counts = defaultdict(int)
    rows=[]
    for path in files:
        digest=sha256(path); counts[digest]+=1; preview,error=extract_preview(path)
        category=normalized_category(path.parent, incoming)
        historical = "histor" in str(path).casefold() or bool(re.search(r"\b(?:2020|2023|2024)\b", path.name))
        structured = path.suffix.casefold()==".docx"
        classification = "unreadable/quarantined" if error else "structured/team-created secondary source" if structured else "historical/superseded" if historical else "exact duplicate" if digest in raw_hashes or digest in registry_hashes else "new candidate"
        rows.append({"original_relative_path":str(path.relative_to(incoming)),"filename":path.name,"category":path.parent.name,"normalized_category":category,"mime_type":MIME[path.suffix.casefold()],"size":path.stat().st_size,"sha256":digest,"detected_title":preview,"standard_order_identifiers":re.findall(r"\b(?:IS\s*\d{3,6}(?:\s*Part\s*\d+)?|S\.O\.\s*\d+\s*\(E\))\b",preview,re.I),"visible_dates":re.findall(r"\b(?:19|20)\d{2}\b",preview),"source_authority_evidence":"unverified; audit does not infer authority from filename","version_status":"historical" if historical else "unverified_currentness","duplicate_relationship":raw_hashes.get(digest) or registry_hashes.get(digest) or "","proposed_canonical_filename":path.name,"classification":classification,"extraction_error":error,"searchable_only_if_explicitly_historical":historical})
    for row in rows:
        if counts[row["sha256"]] > 1 and row["classification"] == "new candidate": row["classification"]="exact duplicate"
    return rows

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("incoming", type=Path); parser.add_argument("--out", type=Path, required=True); args=parser.parse_args()
    rows=audit(args.incoming, ROOT/"data/raw", ROOT/"data/processed/generated_v3/source_registry.json")
    summary={"total_files":len(rows),"by_classification":dict(sorted((key,sum(r["classification"]==key for r in rows)) for key in {r["classification"] for r in rows})),"records":rows}
    args.out.parent.mkdir(parents=True,exist_ok=True); args.out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    args.out.with_suffix(".md").write_text("# Incoming corpus audit\n\n"+"\n".join(f"- `{r['original_relative_path']}` — **{r['classification']}**" for r in rows)+"\n",encoding="utf-8")
if __name__=="__main__": main()
