# V4 final promotion readiness

**READY FOR MANUAL PROMOTION REVIEW** — this does not authorize activation.

Candidate `data/chroma_v4_candidate_01346f7d11f1` /
`bis_corpus_v4_candidate_01346f7d11f1`: 1,160 records, 1,084 eligible, 15 source identities. Corpus SHA: `01346f7d11f12d3c92d2bfa78afe41303f19ff60e29761ef0c4a181613b443a2`; manifest SHA: `0541AEDE22946BB6534CFFA729A7E01F791D4520ED6D44A0466FBD55695239EA`.

- Retrieval 44/44; Top-1 88.24%; Top-3/Top-5 100%; MRR 0.9412.
- Languages: English 30/30; Hindi, Marathi, Tamil 4/4 each; Bengali 2/2.
- V3/V4 regression 6/6; candidate response safety 28/28; backend discovery 487 tests, OK (one OCR-image-only skip).
- FMCS OCR pages retain sidecar provenance. Lab and fee snapshots remain live-verification limited.

Old candidate `f899313eaaac` is permanently blocked by missing retrieval eligibility. Before any separate promotion procedure, take a reviewed backup and preserve rollback to active V3. The dense battery Top-5 lacks `IS 15644` in both V3 and V4; this is a baseline limitation, not a V4 regression.
