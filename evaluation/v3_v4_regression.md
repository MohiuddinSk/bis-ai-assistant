# Read-only V3 versus V4 toy regression

V3: `data/chroma` / `bis_toys_v3_e73aab14a72f7908_39b347ab687e`.
V4: `data/chroma_v4_candidate_01346f7d11f1` /
`bis_corpus_v4_candidate_01346f7d11f1`.

All 6 representative toy queries passed. Each V4 result retained an expected
toy source in the top five, preserved page/source/chunk metadata, and exposed
no excluded V4 source. V3 and V4 top-five source/chunk records are retained in
the accompanying JSON report.

The battery-standard probe did not contain the declared `IS 15644` identifier
in either V3 or V4 top five; it is recorded as a pre-existing baseline-evidence
limitation, not a V4 identifier regression.
