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

## Hybrid Intelligent Grounded RAG

Dated 27 September 2026. This section records the unstaged hybrid assistant work on top of the earlier Phase 2 notes and the unstaged Phase 1 synthesis. It does not replace the Q11 audit history above.

### 1. Executive summary

BIS Saarthi now separates conversation from compliance. Greetings, thanks, goodbye, capabilities, and out-of-scope chat are answered from reviewed copy in English, Hindi, Marathi, Tamil, and Bengali, with no retrieval and no provider call. Known safety-sensitive routes still use deterministic EvidencePlan and FactPlan answers. Questions that do not match those routes can be answered from retrieved evidence by extracting verbatim grounded claims, without adding a new question template. Optional provider synthesis still rewrites only approved facts, and only when `LLM_SYNTHESIS_ENABLED=true`.

### 2. Product scope and honest limitations

The indexed corpus used by this prototype is toy-related BIS material. The assistant says that it is not BIS, that it is not an official legal determination, and that final requirements should be verified with BIS or a qualified professional. It does not claim to cover every BIS product or service. New product categories become answerable only after their documents are ingested.

### 3. Current branch and base commit

- Branch: `feature/hybrid-grounded-rag-synthesis`
- HEAD: `f0d44a42feaba3af2ec1bf166c3c5af9af9327e0` (`fix: improve grounded multilingual answer quality (#59)`)

### 4. Working-tree status

All of this work is unstaged. Phase 1 synthesis files remain in the working tree and were not discarded.

### 5. Architecture before and after

Before: complete plans returned deterministic answers, and incomplete plans either called the legacy generator or failed closed. Social messages were not a first-class route.

After:

User request → conversation router → bounded question understanding → retrieval → deterministic FactPlan when the route is complete → otherwise verbatim grounded-claim extraction for general questions → optional validated synthesis → cited response, clarification, or safe limitation.

### 6. Conversation routing

Closed kinds: greeting, thanks, goodbye, capabilities, compliance_question, follow_up, clarification_response, out_of_scope. Social kinds return `generation_mode=conversation`, no citations, and keep any existing assistant context. The UI shows “BIS Saarthi” instead of a grounded or insufficient badge. Capabilities mention standards, certification, citations, source PDFs, the Compliance Wizard, the Compliance Passport, the five languages, and the current toy scope.

### 7. Deterministic FactPlan behavior

Reviewed routes such as battery standards, non-electric standards, certification, documents, exemptions, commencement, transition, explanations, and wizard roadmaps still use the existing planners. A provider failure on a complete plan still returns that deterministic answer and does not become a 5xx.

### 8. Generic dynamic-claim behavior

For a general question with supporting chunks, the backend selects 20–500 character verbatim spans, drops instruction-like passages, drops near-duplicates, and publishes citation metadata only from TrustedEvidence. Claim identifiers travel as fact IDs in the synthesis packet. A future-document fixture for IS 88001 is answered with no new intent enum.

### 9. Provider synthesis and repair

`LLM_SYNTHESIS_ENABLED` remains default false. A key alone does not enable synthesis. Groq and OpenAI-compatible providers still use the closed four-section synthesis schema for the first call and the one repair. The legacy incomplete-plan schema is unchanged. Stronger modality is rejected unless the approved text contains it.

### 10. Multilingual behavior

Conversational copy exists in all five languages. Reviewed deterministic localization is unchanged for known routes. Generic claim text stays in the evidence language. For a non-English generic answer, the reviewed “shown in English” notice is added rather than machine-translating the quote. Hindi and Marathi are selected by the requested locale, not by script alone.

### 11. Citation and provenance

Filenames, pages, chunk IDs, and excerpts on a grounded answer come from the backend evidence record. The provider cannot supply them. User profile text is not evidence.

### 12. Compliance Wizard and Passport

Wizard routing still enters chat with a server-owned routing context, so social classification does not intercept it. Passport and print components were not rewritten. Frontend wizard and passport tests passed in the frontend suite. A live browser print was not run in this turn.

### 13. Environment variables

No new variable. Existing name only: `LLM_SYNTHESIS_ENABLED`.

### 14. Default off behavior

Unset, empty, `false`, `yes`, and `1` leave synthesis off. Only the exact value `true` enables it.

### 15. Exact changed files

Modified: `.env.example`, `.github/workflows/quality-gates.yml`, `backend/chat_service.py`, `backend/generation.py`, `backend/openai_compatible_generator.py`, `backend/prompts.py`, `backend/question_understanding.py`, `backend/schemas.py`, `backend/settings.py`, `compose.yaml`, `frontend/src/components/ChatMessage.tsx`, `frontend/src/components/ChatMessage.test.tsx`, `frontend/src/i18n/translations.ts`, `frontend/src/types/chat.ts`, `tests/test_ci_configuration.py`, `tests/test_container_configuration.py`, `tests/test_generation_factory.py`, `docs/PHASE2_CURSOR_HANDOFF.md`.

Untracked: `backend/conversation.py`, `backend/grounded_claims.py`, `tests/test_synthesis.py`, `tests/test_hybrid_intelligence.py`.

### 16. New tests

`tests/test_hybrid_intelligence.py` covers multilingual greetings, thanks, goodbye, capabilities, out-of-scope, provider-disabled conversation, the future-document fixture, malicious retrieved text, modality, duplicates, follow-up retrieval, and preservation of the battery FactPlan. `tests/test_synthesis.py` remains the Phase 1 synthesis suite.

### 17. Actual test totals

- Focused hybrid module: 8 tests, OK.
- `python -m unittest discover -s tests`: 427 tests in 78.731s, OK.
- Frontend `npm run lint`: OK.
- Frontend `npm run test -- --run`: 7 files, 97 tests, OK.
- Frontend `npm run build`: OK.
- `git diff --check`: no whitespace errors.

### 18. Manual acceptance results

Run in-process with the provider unavailable and a fixture retriever, not against a live Groq key:

| Example | Result |
|---|---|
| Hi | `conversation`, 0 citations, 2 sections. Identifies BIS Saarthi, toy scope, and that it is not BIS. |
| What can you help me with? | `conversation`, 0 citations. Names standards, certification, citations, PDFs, Wizard, Passport, and five languages. |
| Battery paraphrase “runs on batteries” | `extractive_fallback`, model `extractive-evidence-fallback`, 2 citations, 2 sections. Names IS 15644 and IS 9873 where applicable. |
| What documents are required for a new toy series? | On the battery-only fixture with no provider: HTTP 503. The real-data documents route remains covered by the discovery suite and was not given invented document text. |
| What should I do next? after the battery question | `extractive_fallback`, 2 citations. Reuses the battery FactPlan. |
| Future plush-toy marking note | `extractive_fallback`, 1 citation, 3 sections. Quotes IS 88001 with may, only, and where applicable. No API-key text. |
| How are steel bridges certified? | Clarification asking whether the product is a children's toy and which power type it uses. No invented bridge standard. |
| Hi / नमस्ते / नमस्कार / வணக்கம் / নমস্কার | `conversation`, 0 citations, BIS Saarthi present. |
| Wizard → Passport → Print | Not executed in a browser. Frontend wizard and passport tests passed. |

Synthesis was off, so these grounded examples have no `synthesis_attempt` log. A successful enabled synthesis logs `event=synthesis_attempt ... outcome=success code=OK`.

### 19. Safe observability

`event=synthesis_attempt provider=<groq|openai_compatible|provider> model=<configured model> plan_category=<route> attempt=<1|2> outcome=<success|provider_error|parse_error|validation_error|fallback> code=<fixed code> elapsed_ms=<n>`

### 20. Known limitations

- Generic answers in Hindi, Marathi, Tamil, and Bengali keep the evidence wording and add the reviewed English-fallback notice. They are not newly machine-translated.
- A documents question on a retriever that only holds battery evidence, with no provider, returns 503 instead of a documents FactPlan.
- “What should I do next?” is answered by re-planning the prior question, not by inventing new actions.
- Live Groq was not called in this turn. The running container was not rebuilt.

### 21. Deployment requirements

Rebuild and restart the backend image before a deployed demo can serve this code. Leave `LLM_SYNTHESIS_ENABLED` unset or `false` unless synthesis is intentionally turned on. Do not bake a provider key into the image.

### 22. Rollback and fallback

Social replies do not depend on the provider. Complete plans fall back to the deterministic answer. Generic claims fall back to the verbatim extractive answer. If claims cannot be supported, the previous clarification, abstention, or incomplete-plan generator path remains. Setting `LLM_SYNTHESIS_ENABLED` back to false disables synthesis without removing claim extraction.

### 23. Protected-path status

`git status --short -- data/raw data/processed data/chroma evaluation .env` was empty.

### 24. Git publication status

Nothing was staged, committed, pushed, merged, or deployed.

### 25. Exact next recommended step

Review the unstaged diff. Only with explicit approval, stage the listed files, commit, push the feature branch, and rebuild the backend image. Then repeat one English grounded question with `LLM_SYNTHESIS_ENABLED=true` and confirm a single `synthesis_attempt` success log before enabling synthesis in any shared demo.

### 26. Definition-of-Done repair update (27 September 2026)

- **Resolved HTTP 503 path:** an incomplete deterministic plan now attempts only
  validated dynamic-claim extraction. If claims exist, provider unavailability,
  timeout, rate limiting, authentication/connection failure, invalid output, or
  failed repair returns the evidence-bound extractive response with HTTP 200.
  If no claim can be safely selected, it returns an HTTP 200 limitation. Genuine
  retrieval/infrastructure failures remain 5xx.
- **Generic multilingual behavior:** with synthesis enabled, a provider receives
  the selected language requirement and may produce a citation/fact-bound answer
  in Hindi, Marathi, Tamil, or Bengali. One malformed or wrong-script output is
  repaired once. With synthesis disabled or unsuccessful, generic non-English
  routes return a concise localized limitation; original supporting excerpts are
  still available only through unchanged citation metadata. Reviewed deterministic
  templates remain unchanged.
- **Response semantics:** responses now expose `response_kind` as one of
  `conversation`, `grounded_guidance`, `clarification`, or `limitation`.
  Conversation has no citations and is not presented as grounded guidance.
- **Focused validation completed:**
  `docker compose run --rm -v "${PWD}:/workspace" -w /workspace backend python -m unittest tests.test_hybrid_intelligence tests.test_synthesis -v`
  ran **31 tests**, all passing. This includes provider unavailable, timeout,
  rate-limit, and invalid-response generic fallbacks; localized generic synthesis
  for hi/mr/ta/bn; extractive locale limitation; malicious-passage rejection;
  and known-plan synthesis regressions.
- **Full validation completed:** `python -m unittest discover -s tests` ran
  **430 tests in 91.960s**, all passing. Frontend lint passed; the frontend
  Vitest suite ran **98 tests** across 7 files, all passing; and the production
  frontend build passed.
- **Not manually verified:** no live Groq credentials were used, no live Groq
  synthesis was exercised, and no browser Wizard → Passport → Print acceptance
  was completed in this repair. Do not claim either as complete.
- **Current working tree:** all work remains unstaged. No commit, push, merge,
  deployment, protected-data/index/evaluation edit, or service stop was made.

### 27. Manual Groq/browser acceptance commands (do not run without credentials)

In a deliberately configured local environment with a valid `GROQ_API_KEY` and
`LLM_SYNTHESIS_ENABLED=true`, start the backend by the project’s normal local
command, then issue these requests against `http://127.0.0.1:8000/api/chat`:

```powershell
$Chat = "http://127.0.0.1:8000/api/chat"
function Ask-Bis([string]$Question, [string]$Language = "en") {
  Invoke-RestMethod -Method Post -Uri $Chat -ContentType "application/json" -Body (@{ question = $Question; response_language = $Language } | ConvertTo-Json)
}
Ask-Bis "Hi"
Ask-Bis "What can you help me with?"
Ask-Bis "Which standards apply to a battery-operated toy?"
Ask-Bis "What documents are required for a new toy series?"
Ask-Bis "What are the steps to obtain BIS certification for a toy?"
Ask-Bis "What marking note applies to plush toys?"
Ask-Bis "What exact fee applies to a plush-toy marking note?"
Ask-Bis "What marking note applies to plush toys?" "hi"
Ask-Bis "What marking note applies to plush toys?" "mr"
Ask-Bis "What marking note applies to plush toys?" "ta"
Ask-Bis "What marking note applies to plush toys?" "bn"
```

For the follow-up, resend the previous response’s `assistant_context` with
`"What should I do next?"` and verify it does not retrieve unrelated context.
In a browser, complete all five Wizard steps, submit a grounded profile, switch
language, verify Passport details/citations remain intact, then select **Save as
PDF / Print** and confirm the isolated print view contains only the Passport.

### 28. Live-quality repair update (27 September 2026)

- **Live failures addressed:** provider-assisted known plans previously allowed
  the model to rewrite direct facts, procedures, and limitations. This could
  repeat `IS 15644`/`IS 9873`, omit a supported parts list, fuse
  `battery-operated`, or fail a procedural answer on an unsupported modal.
  Generic retrieval could also turn an unrelated high-ranked passage into a
  grounded answer.
- **Locked-section hybrid design:** complete FactPlans now publish the exact
  backend-composed direct answer, next steps, important limitations, section
  citation bindings, and public citation metadata. The provider can contribute
  only one validated, non-repetitive plain-language explanation. It cannot add
  identifiers, dates, requirements, absence claims, or change a locked section.
  `generation_mode=llm` is used only when that explanation is accepted;
  otherwise the exact deterministic response remains `extractive_fallback`.
- **Generic relevance gate:** generic claims must answer at least one
  distinctive question concept after generic BIS/toy/standard vocabulary is
  removed. Missing relevance emits fixed diagnostic
  `QUESTION_NOT_ANSWERED`, returns an HTTP 200 limitation, and does not expose
  citations or raw passages as an answer. The acoustic-subcontracting case is
  therefore a limitation unless selected evidence actually addresses acoustic
  testing and subcontracting (or reviewed equivalents).
- **Raw-passage prohibition:** provider failure or disabled synthesis renders
  only individually validated claim text. It never prefixes or concatenates a
  retrieved passage. With no directly answering claim it returns a localized
  limitation; evidence excerpts remain metadata only.
- **Focused validation:** synthesis, hybrid, and real-index suites ran **39
  tests**, all passing. The chat API suite ran **53 tests**, and the
  OpenAI-compatible provider suite ran **53 tests**, both passing. This includes
  locked document/certification procedure checks, generic provider failures,
  the future `IS 88001` fixture, malicious-passage rejection, and irrelevant
  acoustic evidence.
- **Full backend discovery:** `python -m unittest discover -s tests` ran
  **432 tests in 96.527s**, all passing.
- **Still manual:** no live Groq credential was used and no browser Wizard →
  Passport → Print walkthrough was performed. The manual commands in section
  27 remain the acceptance procedure; do not state that live or browser
  acceptance is complete.
- **Publication status:** nothing has been staged, committed, pushed, merged,
  or deployed. Protected data/index/evaluation paths remain out of scope.

### 29. Generic relevance hardening (27 September 2026)

- **Live acoustic failure:** a generic acoustic-subcontracting question was
  incorrectly published as grounded guidance from unrelated washable-toy,
  conformity, age-grading, and licence-scope passages. Citations proved those
  passages existed, not that they answered the question.
- **Question-anchor coverage:** generic claim selection now Unicode-normalizes
  the question, drops generic BIS/toy/standard and question wording, and uses
  conservative reviewed synonym groups only for evidence matching. A permission
  question about acoustic testing and subcontracting must cover both the
  acoustic/sound/noise subject and subcontract/outsource relation before it can
  be grounded. No anchor coverage returns a citation-free localized limitation.
- **Fixed diagnostics:** `QUESTION_CONCEPT_NOT_COVERED`,
  `DIRECT_ANSWER_NOT_RELEVANT`, and
  `SELF_DECLARED_INSUFFICIENT_EVIDENCE` are used at the generic publication
  boundary. Long raw-passage-sized spans are rejected during claim selection;
  raw retrieval text is never used as an answer.
- **Controls:** irrelevant acoustic evidence returns a limitation with no
  citations or unrelated text. The supported higher-age-grading question remains
  grounded and reports that requests to avoid tests by declaring a higher age
  grading are not entertained. The future `IS 88001` claim fixture remains
  grounded; non-English generic limitations remain localized.
- **Focused validation:** hybrid, synthesis, real-index, and chat API suites
  ran **95 tests in 12.656s**, all passing. Live Groq and browser acceptance
  remain unperformed; use the manual procedure in section 27 before claiming
  either.
- **Full backend discovery:** **435 tests in 97.155s**, all passing.

### 30. Generic answer rendering polish (27 September 2026)

- The supported higher-age-grading response now publishes one concise
  user-facing proposition rather than repeated source-like passages. Its
  limitation is evidence-specific: the cited material does not describe
  penalties or enforcement consequences. It no longer adds unrelated fee,
  form, laboratory, or timeline boilerplate.
- Verbatim supporting quotes remain citation excerpts only. Generic claim
  selection suppresses duplicate propositions and refuses passage-sized claims;
  deterministic known-plan output remains unchanged.
- Focused hybrid, synthesis, and real-index tests: **42 passed in 9.237s**.

### 31. Full-suite document and transition repair (27 September 2026)

- New-series documents retain locked backend facts, steps, limitations,
  citations, and evidence metadata. The stale zero-provider-call assertion was
  replaced with an invalid-provider regression: two malformed synthesis attempts
  return the exact deterministic fallback.
- Transition Facilitation Order guidance is explicitly synthesis-ineligible.
  Its operative legal roles, conditions, and dates remain deterministic and the
  existing zero-provider-call behavior is preserved.
- Focused real-index and synthesis suites: **27 passed in 9.067s**.
