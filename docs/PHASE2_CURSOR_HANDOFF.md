# Phase 2 Cursor Handoff

## Repository and runtime

- Local repository: `C:\Users\Admin\Downloads\BIS_AI_Assistant_Repaired_v3_ready\bis-ai-assistant`
- GitHub: `https://github.com/MohiuddinSk/bis-ai-assistant.git`
- Branch: `feature/evidence-rich-deterministic-answers`
- Intended Phase 2 Python command: `..\venv-audit\Scripts\python.exe`.
- Working interpreter used in this validation turn: `.\.venv-audit\Scripts\python.exe` → Python 3.11.9. The parent path `..\venv-audit\Scripts\python.exe` remains absent. Do not assume a different active `(venv)` works. Do not alter dependencies.
- Docker was not started and is not required for the unit/integration suite.

## Safety and scope

- Protected, unchanged paths: `data/raw`, `data/processed`, `data/chroma`, and `evaluation`.
- Do not rebuild the Chroma index or embeddings. Do not modify dependencies.
- Preserve all existing working-tree edits. Do not stage, commit, push, merge, deploy, or start Docker during the audit repair.
- `.venv-audit` must never be staged.
- The historical baseline audit document must remain unchanged.

## Phase 2 implementation summary

The production implementation already contains deterministic, grounded explanations for IS 15644 and IS 9873, controlled question understanding, and structured answer sections. Q03 and Q05 were repaired to audit as GOOD. Q10’s deterministic certification path remains grounded. Q11 has a distinct `explain_secondary_part_list` route for an explicit request for applicable IS 9873 parts for a battery-operated toy.

Q11 parses evidence rather than user-supplied values, fails closed if the required evidence is absent, and renders only Parts 2, 3, 4, 9, 10, and 11. Rows containing Parts 1 or 7 cannot satisfy the exact-list role. IS 15644 remains the cited primary standard for electric toys. Battery-operated wording is controlled user context and is uncited. Q11 public citations are pruned to the first-seen ordered union of finalized cited section IDs. Mixed rows may support an electric-route/applicability role only when their own text explicitly does so; they never support the exact list.

The Q11 exact-list retrieval/ranking expansion is isolated to explicit Q11-style requests. It does not activate for battery roadmaps. Battery roadmap fallback preserves route-specific standards, selected evidence, citations, and an uncited controlled power-context section.

Grounding controls remain strict: citation IDs must map to public citations, generated quotes are validated, user text is not evidence, exact parts are parsed from selected text, and failures fail closed. Do not weaken `_validate_sections`, citation mapping, quote validation, or audit citation integrity.

## Debugging history and completed root causes

| Issue | Root cause | Repair |
|---|---|---|
| Explanation-title normalization | Final section title normalization obscured structured headings. | Preserve controlled context and test against finalized content where appropriate. |
| Q11 exact-list selection | Generic secondary selection chose broad/non-electric rows. | Add a strict exact-list role and parser; reject extra Parts 1/7. |
| Q11 grounded abstention | `secondary_applicability` was required although plan provided `product_applicability`. | Wire the selected applicability role through deterministic composition. |
| Unused Q11 citation | Planning identity evidence could remain in public citations without a finalized section. | Prune Q11 public citations to finalized cited-section order. |
| Battery wording in cited claim | Controlled battery context leaked into a cited primary statement. | Keep battery wording only in uncited controlled context. |
| Roadmap leakage | Q11 candidate expansion/scoring applied to all electric routes and could crowd fixed-budget roadmap evidence. | Scope those boosts to an explicit Q11 request. |
| Current audit near-tie nondeterminism | Public `ranked_candidates` serialized a vector top-10 boundary whose membership varies for near ties. | Audit now serializes a stable boundary-sensitive marker while retaining the internal probe for classification. |
| Incorrect `SUPPORTED` missing fact | A supported non-loss diagnostic state was emitted as a missing-fact row. | Exclude `SUPPORTED` from serialized `missing_facts`; it counts as satisfied. |

## Important Q11 semantics

- Exact cited list: IS 9873 Parts 2, 3, 4, 9, 10, and 11.
- Exact-list evidence alone supports that set. Any parsed extra part, including 1 or 7, fails the role.
- Primary role: IS 15644 for electric toys, cited.
- Applicability role: must be electric-route evidence where used, cited.
- Battery-operated wording: user-provided context only, in a separate uncited section.
- The response does not establish complete clause-level applicability or that every listed part applies to every toy.
- The Q11 route must not affect `roadmap_battery`, `roadmap_mains`, or ordinary `explain_secondary_part` behavior.

## Audit repair in this turn

Only these audit files were intentionally edited in this turn before writing this handoff:

- `scripts/audit_answer_coverage.py`
- `tests/test_answer_coverage_audit.py`
- `docs/PHASE2_CURSOR_HANDOFF.md`

Audit behavior changed as follows:

1. The internal ten-result ranking probe is still used by `_classify` to distinguish ranking from retrieval loss, but serialized `ranked_candidates` is now a stable marker (`boundary_sensitive_probe`) rather than unstable top-N membership.
2. A fact whose diagnostic cause is `SUPPORTED` is not emitted in `missing_facts`.
3. Tests were added for boundary-varying diagnostic normalization and for two byte-identical fresh CLI reports with Q11 expected as `GOOD / CORRECT_LIMITATION / []`.

## Current validation status

Validated in this turn with `$Phase2Python = ".\.venv-audit\Scripts\python.exe"` (Python 3.11.9). `git diff --check` reports only CRLF checkout warnings, no patch whitespace errors. Harmless environment warnings: Starlette/httpx compatibility noise and Chroma/Pydantic warnings.

| Check | Result |
|---|---|
| `tests.test_answer_coverage_audit` | Ran 11 tests in 51.216s — OK |
| Two independent CLI audits | collection=917; SHA-256 match |
| Q11 JSON | `GOOD` / `CORRECT_LIMITATION` / `missing_facts=[]` |
| Expanded Phase 2 module list | Ran 183 tests in 74.706s — OK |
| `unittest discover -s tests` | Ran 386 tests in 73.120s — OK |

The expanded module list is 183 tests, not the earlier 181-test figure, because this checkout includes the additional audit-determinism and Q11 evidence-selection tests.

## Marker review

`_ranked_candidate_diagnostic` ignores candidate membership and always returns `{"kind": "boundary_sensitive_probe", "serialized_candidates": false}`. The internal `retriever.search(..., k=10)` probe is still passed to `_classify` to distinguish `RANKING_MISS` from `RETRIEVAL_MISS`. Serialized `retrieved`, `selected_evidence_ids`, `answer`, `answer_sections`, `citations`, `citation_integrity`, and `_quality(...)` are unchanged by the marker. Production backend files were not edited in this validation turn.

## Audit status

- Collection count: 917.
- Audit questions: Q01–Q12 (12 total).
- Audit 1 SHA-256: `5ECF64709AC6A416C4974F3D694EA1645E5F72133702A555BF19C15A1F07505B`
- Audit 2 SHA-256: `5ECF64709AC6A416C4974F3D694EA1645E5F72133702A555BF19C15A1F07505B`
- Hash match: yes.
- Q11: `quality=GOOD`, `primary_cause=CORRECT_LIMITATION`, `missing_facts=[]`.
- Protected paths (`data/raw`, `data/processed`, `data/chroma`, `evaluation`): unchanged (`git status --short --` empty).
- Remaining blocker: none for validation. Staging, commit, push, PR, merge, and deploy still require explicit approval.

Factual Q01–Q12 table from `$env:TEMP\bis-phase2-cursor-1.json`:

| id | quality | primary_cause | missing_facts |
|---|---|---|---|
| Q01 | USABLE_BUT_THIN | SOURCE_ABSENT | next action |
| Q02 | GOOD | CORRECT_LIMITATION | (none) |
| Q03 | GOOD | CORRECT_LIMITATION | (none) |
| Q04 | GOOD | CORRECT_LIMITATION | (none) |
| Q05 | GOOD | CORRECT_LIMITATION | (none) |
| Q06 | CORRECTLY_LIMITED | CORRECT_LIMITATION | comparison limitation |
| Q07 | CORRECTLY_LIMITED | CORRECT_LIMITATION | partial-list limitation |
| Q08 | USABLE_BUT_THIN | SOURCE_ABSENT | direct conditional answer; handmade-alone limit |
| Q09 | CORRECTLY_LIMITED | EXTRACTION_MISSING | operative permission; conditions; limitation |
| Q10 | GOOD | CORRECT_LIMITATION | (none) |
| Q11 | GOOD | CORRECT_LIMITATION | (none) |
| Q12 | CORRECTLY_LIMITED | SOURCE_ABSENT | immediate action; conditional limitation |

## Current working tree

Actual `git status --short` after validation (no staging):

```text
 M backend/chat_service.py
 M backend/question_understanding.py
 M scripts/audit_answer_coverage.py
 M tests/test_answer_coverage_audit.py
 M tests/test_standard_explanation.py
?? docs/PHASE2_CURSOR_HANDOFF.md
?? tests/test_q11_evidence_selection.py
```

The first, second, fifth, and seventh entries are existing Phase 2 production/test work and are outside this audit-only repair scope. Preserve them. Re-run status before staging because this is a live working tree.

## Copy-paste commands

Set the approved interpreter after verifying its path. The requested parent path is shown first; if it is unavailable, stop and repair/select the approved existing interpreter instead of installing dependencies.

```powershell
$Phase2Python = ".\.venv-audit\Scripts\python.exe"
Test-Path $Phase2Python
& $Phase2Python -m unittest tests.test_answer_coverage_audit -v
if ($LASTEXITCODE -ne 0) { throw "Answer coverage audit tests failed" }

& $Phase2Python -m unittest tests.test_q11_evidence_selection -v
if ($LASTEXITCODE -ne 0) { throw "Q11 tests failed" }

& $Phase2Python -m unittest `
  tests.test_chat_api `
  tests.test_compliance_api `
  tests.test_compliance_real_data_integration `
  tests.test_real_data_integration `
  tests.test_standard_explanation `
  tests.test_provider_disabled_api `
  tests.test_retrieval_provider_contract `
  tests.test_guided_fact_plan `
  tests.test_question_understanding `
  tests.test_question_understanding_real_data `
  tests.test_answer_coverage_audit `
  tests.test_q11_evidence_selection -v
if ($LASTEXITCODE -ne 0) { throw "Expanded Phase 2 regression suite failed" }

& $Phase2Python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Full test discovery failed" }
```

Double-audit SHA comparison and Q11 verification:

```powershell
$Audit1 = "$env:TEMP\bis-phase2-final-deterministic-1.json"
$Audit2 = "$env:TEMP\bis-phase2-final-deterministic-2.json"
& $Phase2Python .\scripts\audit_answer_coverage.py --output $Audit1
if ($LASTEXITCODE -ne 0) { throw "First audit failed" }
& $Phase2Python .\scripts\audit_answer_coverage.py --output $Audit2
if ($LASTEXITCODE -ne 0) { throw "Second audit failed" }
$Hashes = Get-FileHash $Audit1, $Audit2
$Hashes | Format-Table Path, Hash
if ($Hashes[0].Hash -ne $Hashes[1].Hash) { throw "Audit output remains nondeterministic" }
$Audit = Get-Content $Audit1 -Raw | ConvertFrom-Json
$Q11 = $Audit.questions | Where-Object { $_.id -eq "Q11" }
$Q11 | Select-Object id, quality, primary_cause, missing_facts | Format-List
if ($Q11.quality -ne "GOOD") { throw "Q11 quality is not GOOD" }
if ($Q11.primary_cause -ne "CORRECT_LIMITATION") { throw "Q11 primary cause is incorrect" }
if (@($Q11.missing_facts).Count -ne 0) { throw "Q11 still has missing facts" }
```

Repository and protected-path checks:

```powershell
git diff --check
git status --short -- data/raw data/processed data/chroma evaluation
git diff --stat
git status --short
git diff --name-only
```

Only after every check passes and explicit approval is received, stage exactly the intended files:

```powershell
git add backend/chat_service.py backend/question_understanding.py scripts/audit_answer_coverage.py tests/test_answer_coverage_audit.py tests/test_standard_explanation.py tests/test_q11_evidence_selection.py docs/PHASE2_CURSOR_HANDOFF.md
```

Suggested commit message: `fix: stabilize phase 2 evidence coverage audit`.

## Exact next steps for Cursor

Validation steps 1–7 are complete. Remaining:

1. Only with explicit approval, stage the exact files, commit, push the feature branch, create/review a PR, and merge after checks pass.
2. Deployment and live frontend/API verification occur only after merge.

## Known good state checklist

- [x] Protected paths unchanged.
- [x] No index/embedding or dependency change.
- [x] Q11 exact list remains 2, 3, 4, 9, 10, 11 only.
- [x] Q11 mixed extra-part rows cannot support the exact list.
- [x] Q11 battery context remains uncited.
- [x] Q11 public citations equal finalized cited-section IDs in first-seen order.
- [x] Battery roadmap remains isolated from Q11 ranking expansion.
- [x] Audit output hashes match across fresh processes.
- [x] Q11 audits as GOOD / CORRECT_LIMITATION / no missing facts.
- [x] Expanded suite and full discovery pass.

## Do not do

- Do not stage `.venv-audit`.
- Do not modify protected data, the historical baseline audit, index, embeddings, dependencies, API schema, frontend, or Docker configuration for this repair.
- Do not suppress validation failures or weaken grounding/citation checks to make tests pass.
- Do not hard-code chunk IDs, pages, ranks, filenames, excerpts, or citations.
- Do not claim unrun tests or unverified audit hashes passed.
