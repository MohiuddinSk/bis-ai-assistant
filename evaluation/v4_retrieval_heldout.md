# V4 held-out retrieval evaluation

Candidate: `bis_corpus_v4_candidate_01346f7d11f1` at
`data/chroma_v4_candidate_01346f7d11f1`.

- 44 cases passed out of 44.
- Top-1: 88.24%; Top-3: 100%; Top-5: 100%; MRR: 0.9412.
- The original 32 cases remained 32/32. The 12 held-out cases included five
  fee paraphrases (English, Hindi, Marathi, Tamil, Bengali), generic
  certification, and toy/FMCS/jewellery/helmet/lab/cross-category controls.
- No forbidden-source, FMCS-scope, or lab/fee freshness metadata violations
  were reported by the fixture evaluator.

Language outcomes: English 30/30, Hindi 4/4, Marathi 4/4, Tamil 4/4, and
Bengali 2/2. This bounded set is a regression gate, not a statistical claim.
