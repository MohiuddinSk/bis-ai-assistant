"""Offline Poppler/Tesseract smoke test for the dedicated ingestion image."""
from __future__ import annotations
import hashlib,json,re,subprocess,tempfile
from pathlib import Path
EXPECTED="BIS SAARTHI OCR TEST 4151"
def run(args): return subprocess.run(args,capture_output=True,text=True,check=False)
def pdf(path):
 content=b"BT /F1 24 Tf 72 700 Td (BIS SAARTHI OCR TEST 4151) Tj ET\n"
 objs=[b"<< /Type /Catalog /Pages 2 0 R >>",b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",b"<< /Length %d >>\nstream\n%s endstream"%(len(content),content)]
 data=bytearray(b"%PDF-1.4\n"); offsets=[0]
 for i,obj in enumerate(objs,1): offsets.append(len(data));data+=f"{i} 0 obj\n".encode()+obj+b"\nendobj\n"
 start=len(data);data+=b"xref\n0 6\n0000000000 65535 f \n"+b"".join(f"{x:010d} 00000 n \n".encode() for x in offsets[1:]);data+=f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode();path.write_bytes(data)
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 with tempfile.TemporaryDirectory() as d:
  root=Path(d); source=root/'smoke.pdf';pdf(source); prefix=root/'page'; render=run(['pdftoppm','-r','300','-png',str(source),str(prefix)]); image=root/'page-1.png'; ocr=run(['tesseract',str(image),'stdout','-l','eng','--oem','1','--psm','6']) if render.returncode==0 else None
  extracted=re.sub(r'\s+',' ',ocr.stdout).strip() if ocr else ''
  result={'success':bool(ocr and ocr.returncode==0 and EXPECTED in extracted),'expected_text':EXPECTED,'extracted_text':extracted,'pdftoppm_exit_code':render.returncode,'tesseract_exit_code':None if ocr is None else ocr.returncode,'tool_versions':{'tesseract':run(['tesseract','--version']).stdout.splitlines()[0],'pdftoppm':run(['pdftoppm','-v']).stderr.splitlines()[0]},'temporary_file_hashes':{'pdf':h(source),'png':h(image) if image.exists() else None},'stderr':{'pdftoppm':render.stderr,'tesseract':'' if ocr is None else ocr.stderr}}
  print(json.dumps(result,ensure_ascii=False));return 0 if result['success'] else 1
if __name__=='__main__':raise SystemExit(main())
