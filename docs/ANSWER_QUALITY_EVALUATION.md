# Answer-quality evaluation

## Read-only retrieval baseline — 2026-09-11

The ten information needs in `evaluation/questions.json` all pass the existing read-only evidence-location regression (10/10). That measures retrieval location, not guaranteed provider-answer completeness.

| Information need | Expected evidence | Result | Safe behavior |
| --- | --- | --- | --- |
| Applicable standards | Product manual standard table | Retrieved | Compose only with complete primary/secondary roles. |
| New toy series documents | Manual pages 5 and 58–60 | Retrieved | List only selected, evidence-backed documents. |
| Artisan exemption | 2020 amendment | Retrieved | Preserve sale, registration, and authority conditions. |
| Dates and transition orders | Relevant order | Retrieved | Preserve exact supported dates and scope. |
| R&D, testing, latest manual | Relevant order/manual | Retrieved | Abstain when collective evidence is incomplete. |

Provider output remains quote-validated and can safely abstain after invalid or incomplete evidence; no provider call is required by this evaluation.

## Deterministic composition follow-up — 2026-09-12

The three live abstentions had eight retrieved passages but no complete fallback role plan, so invalid/rejected provider candidates consumed repair latency before safe abstention. Read-only inspection confirmed complete trusted roles for each: Appendix III declaration, series details and fee declaration for a new series; a legal `come into force` clause for commencement; and operative application/permission clauses for the 2026 transition order.

| Question | Result after composition | Classification | Limitation |
| --- | --- | --- | --- |
| New toy-series documents | Qualified three-item checklist | grounded and clear | Does not claim any unshown document is required. |
| QCO commencement | Exact supported legal commencement clause | grounded but incomplete | The phrase “the QCO” remains inherently ambiguous across orders; the response identifies only the retrieved legal clause. |
| 2026 transition order | Scope plus permission-mechanism explanation | grounded and clear | Conditions remain limited to the cited operative passages. |

## Citation-sufficiency correction — 2026-09-12

- The initial new-series declaration excerpt was a form heading/date field. It was replaced with substantive `I hereby declare` language, and the response now calls the list **partial** rather than complete.
- “The QCO” is ambiguous across the indexed orders. The deterministic response now says the selected extension clause is relative to Gazette publication, does not establish a calendar date, and asks for the specific QCO/order.
- A transition heading (`Grant of permission`) is no longer an operative role. The plan requires the operative sentence identifying the Department, an incorporated company, and risk assessment; the citation retains that full sentence.

- Deterministic prose assembly now joins normalized fragments with one space, preventing layout-boundary defects without changing evidence-derived facts.
