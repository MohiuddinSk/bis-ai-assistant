# Answer coverage audit

## Executed basis

This report is based on the executed `bis-answer-coverage-audit.json`: 12
questions, collection count 917, raw-PDF text check enabled, and no generation
provider. It uses the production retrieval merge and evidence planner. Only
short source/page references are retained; no paths, configuration, or raw
evidence bodies are included.

| ID | Quality | Primary cause | Secondary cause | Retrieved / selected summary |
| --- | --- | --- | --- | --- |
| Q01 | USABLE_BUT_THIN | CORRECT_LIMITATION | SOURCE_ABSENT (next action) | FAQ p1; manual pp3–4; `primary_standard`, `secondary_standard` |
| Q02 | GOOD | TEMPLATE_REDUCED | PLANNER_DROPPED | Guide p8, manual p4, QCO p3; identity/primary/applicability/next step |
| Q03 | UNSUPPORTED | PLANNER_DROPPED | RETRIEVAL_MISS | Manual p41 only; no roles |
| Q04 | GOOD | CORRECT_LIMITATION | — | FAQ p1, manual pp3–4; identity/primary/applicability/secondary/next step |
| Q05 | USABLE_BUT_THIN | RANKING_MISS | TEMPLATE_REDUCED | Manual pp3–4 selected; QCO p3 title at rank 10 |
| Q06 | CORRECTLY_LIMITED | CORRECT_LIMITATION | — | FAQ p1, manual p4, guide p8, QCO p3; comparison roles |
| Q07 | CORRECTLY_LIMITED | CORRECT_LIMITATION | — | Manual pp58–59; declaration/details/fee |
| Q08 | USABLE_BUT_THIN | CORRECT_LIMITATION | matcher false-negative | 2020 amendment p2; exemption/registration/authority |
| Q09 | CORRECTLY_LIMITED | CORRECT_LIMITATION | matcher false-negative | transition order p4; operative scope/permission |
| Q10 | VAGUE | PLANNER_DROPPED | raw result called it TEMPLATE_REDUCED | certification guide p5; four procedure roles |
| Q11 | UNSUPPORTED | PLANNER_DROPPED | RETRIEVAL_MISS | manual pp3–6; no roles |
| Q12 | CORRECTLY_LIMITED | CORRECT_LIMITATION | — | manual pp2,6,22,58; clarification only |

The original JSON’s Q08/Q09 missing-fact labels are not repeated as primary
findings: their final sections visibly contain those facts. They were caused by
the diagnostic’s all-term text matcher, not source/extraction/index loss.

## Active-index integrity

| Metric | Value |
| --- | ---: |
| Chroma directory | `data/chroma` |
| Production collection | `bis_toys_v3_e73aab14a72f7908_39b347ab687e` |
| Collection count | 917 |
| Unique IDs | 917 |
| Unique normalized text hashes | 880 |
| Duplicate normalized texts | 37 extra records in 15 groups |
| Unique source/page/chunk identities | 917 |
| Duplicate source/page/chunk identities | 0 |

917 is expected, not an audit sum or adjacent-chunk expansion: the immutable
manifest declares `retrieval_chunk_count: 917`, and production startup checks
that the active Chroma ID set exactly equals its 917 retrieval-enabled chunks.
The read-only collection-name inventory contains this single production
collection, with count 917; no second generated dataset collection was found.
Docker copies the same `data/chroma` and `data/processed/generated_v3`; both
use the manifest collection and pinned `intfloat/multilingual-e5-small`
revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`.

The identity is source filename, page range, chunk type, and stored text hash.
The duplicate normalized text count is a ranking-quality observation, not an
integrity failure: IDs and source/page/chunk identities are unique.

## Executed traces and safe next steps

### Q01 — Battery-operated standard

- Queries: question; `electric toy applicable primary standard IS 15644`.
- Final sections: **In simple terms** (IS 15644 primary); **What this means for you** (conditional IS 9873 parts).
- Required facts: both standard roles are selected and included. A standalone action is not selected. No improvement should invent one.

### Q02 — Explain IS 15644

- Queries: question; electric-standard coverage. Guide p8 supplies “Safety of Electric Toys”; FAQ p1 supplies the supported electric-function condition. The selected citation is QCO p3.
- Final sections: direct answer, meaning, next step, limitation. Title and applicability exist but the generic limitation says full title is not established.
- Loss: `TEMPLATE_REDUCED` plus title-row `PLANNER_DROPPED`. Safely select/cite the title and condition; full scope/tests still need authoritative standard text.

### Q03 — When IS 15644 applies

- Query: question only; eight manual p41 test chunks are returned, but no plan role or section is produced and the provider-disabled path stops it.
- Loss: `PLANNER_DROPPED`; applicability is `RETRIEVAL_MISS`. Route this wording to the existing explanation plan.

### Q04 — Explain IS 9873 Part 1

- Queries: question; non-electric coverage. FAQ p1/manual pp3–4 select identity, primary non-electric role, conditional secondary relationship, and next step.
- Final sections: direct, two explanations, next step, limitation. No selected fact is lost; full scope remains a `CORRECT_LIMITATION`.

### Q05 — Explain IS 9873 Part 2

- Queries: question; secondary-standard coverage. Manual pp3–4 supplies selected conditional role. QCO p3 at rank 10 says “Safety of Toys Part 2 Flammability.”
- Final sections: direct, meaning, next step, limitation. Title/purpose is indexed but below cutoff: `RANKING_MISS`; add it only through an explicit selected role.

### Q06 — Comparison

- Queries: question; electric and non-electric coverage. Selected material supports electric versus non-electric primary roles.
- Final sections: direct role distinction, explanation, limitation. It does not support clause-level/full-scope comparison: `CORRECT_LIMITATION`; do not enrich beyond this.

### Q07 — New-series documents

- Queries: question; product-manual declaration coverage. Manual p58 provides declaration and separate model/starting-age details; p59 provides extension-fee declaration.
- Final sections: partial-checklist direct answer, three checklist items, limitation. These are distinct facts, not duplicate normalized chunks. All are retained; only completeness is limited.

### Q08 — Handmade exemption

- Queries: question; artisan/registration coverage. Amendment p2 selects manufacture/sale scope, registration, and authority.
- Final sections: direct “not all,” conditional explanation, handmade-alone limitation. Every required condition is visible; the JSON’s two source-absent labels are matcher errors. Broader exemption remains limited.

### Q09 — 2026 transition order

- Queries: question; transition-permission coverage. Order p4 selects operative scope and permission.
- Final sections: conditional permission, DPIIT/company/risk-assessment condition, limitation. It correctly avoids automatic approval; reported extraction/index misses are matcher errors.

### Q10 — Certification steps

- Queries: question; 10-step certification coverage. Guide p5 selects Manakonline, standard selection, application details, and test facilities.
- Final section: only power/type clarification. The facts are selected but preempted before composition: `PLANNER_DROPPED`. Keep clarification if essential; otherwise show a cited, explicitly partial general-step list.

### Q11 — IS 9873 parts for battery toys

- Query: question only. Manual pp3–6 retrieves the part list and battery/electric material, but no plan/section is built.
- Loss: `PLANNER_DROPPED`; explicit conditional phrasing is `RETRIEVAL_MISS`. Route this form to secondary-part planning and retain “where applicable.”

### Q12 — Next action after identifying a standard

- Query: question only; manual pp2,6,22,58 are retrieved. The sole final section requests power type.
- This is `CORRECT_LIMITATION`: without a validated power route, a roadmap could apply the wrong standard.

## Evidence-backed implementation order

| Priority | Questions | Evidence / modules | Improvement | Risk and test |
| --- | --- | --- | --- | --- |
| P0 | Q02, Q10 | Selected/retrieved facts; deterministic composition in `backend/chat_service.py` | Retain title/condition and partial cited steps | Claim-to-citation and qualifier tests |
| P1 | Q03, Q05, Q11 | Existing indexed evidence; intent/query/ranking/planning | Avoid provider-required dead ends | Real-index route/rank tests; no `may` upgrade |
| P2 | Q01, Q02, Q04, Q05, Q07, Q10 | Existing roles | Compact standard/application cards | Per-card citation and profile-isolation tests |
| P3 | Q02, Q04–Q06 | Missing full standards/scope/comparison evidence | Detail only when authoritative sources exist | Provenance/extraction/index tests |
| P4 | Incomplete multi-fact cases | Validated fact cards after P0–P3 | Plain language without synthesis | Provider-disabled fallback validation |

Additional authoritative material is needed for complete scopes, clauses, test
limits, marking, fees, forms, timelines, and genuine requirement-by-requirement
comparisons. Prompt wording cannot supply those facts.
