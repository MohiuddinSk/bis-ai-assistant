# Grounded Chat API Implementation Log

## 2026-09-11 — Role-based answer composition

- Baseline review found the confusing battery wording was an answer-composition issue, not missing evidence: separate IS 15644 primary and IS 9873 secondary passages were already selected, but raw table serialization could leak into the answer.
- A complete standards or artisan evidence-role plan now produces deterministic, readable user-facing composition. Citation excerpts remain backend-controlled and verbatim; table coordinates stay out of the answer.
- The battery path is activated by evidence roles for electric/battery questions, not an exact question match. It labels IS 15644 primary and IS 9873 secondary/additional only when both roles are present.
- Read-only `retrieval/test_retrieval.py` reports 10/10 evidence-location hits. No corpus, embeddings, or Chroma collection was rebuilt.

## 2026-09-12 — Deterministic role plans for former abstentions

- Root cause of the new-series, commencement, and transition abstentions: retrieval returned passages, but no deterministic composer existed. Invalid/incomplete model candidates then used the two-call validation/repair path and safely abstained.
- Added complete trusted role plans for new-series declaration/details/fee, legal commencement clauses, and transition operative scope/permission. Complete plans bypass Groq before generation and retain backend citation mapping and disclaimer.
- The new real-index tests assert `extractive_fallback`, grounded status, trusted citations, and zero fake-provider calls for all three paths.

## 2026-09-12 — Citation sufficiency safeguards

- Deterministic claim roles now reject form headings/date fields and transition headings as support for material claims.
- New-series output is explicitly partial; ambiguous QCO commencement returns a cited limitation rather than silently selecting an exact date; transition permission requires operative eligibility and risk-assessment text.

## 2026-09-12 — Deterministic fragment spacing

- Replaced implicit adjacent string concatenation in checklist and transition composition with a shared fragment joiner. It normalizes each fragment and inserts exactly one boundary space.
- Regression coverage rejects `bedeclared`, `permission maybe granted`, accidental joined words, and double spaces while preserving roles, citations, and provider bypass.

## Objective

Implement and verify a grounded `POST /api/chat` endpoint using the existing singleton BIS Toys Retriever and Groq.

## Current Status

- Status: Blocked
- Branch: `feature/grounded-chat-api`
- Python: 3.11.9
- Groq SDK: 1.7.0
- Groq API key present: No (value was not printed)
- Started: 2026-09-11 13:52:10 +05:30
- Last updated: 2026-09-11 14:10:25 +05:30

## Protected Components

- [x] `data/raw/**` unchanged
- [x] `data/processed/generated_v3/**` unchanged
- [x] `data/chroma/**` not deleted or rebuilt
- [x] `ingestion/**` unchanged
- [x] `retrieval/search.py` unchanged
- [x] `retrieval/embeddings.py` unchanged
- [x] Embedding and ranking contracts unchanged
- [x] `evaluation/retrieval_results.json` preserved and unstaged (no working-tree diff was present on this branch)

## Implementation Checklist

- [x] Git and environment preflight completed
- [x] Existing 24 tests passed before implementation
- [x] Groq SDK version inspected
- [x] Groq SDK structured-output behavior inspected
- [x] Dependency pinned
- [x] Environment template and ignores verified
- [x] Prompt implemented
- [x] Generator protocol and Groq provider implemented
- [x] Chat service and citation validation implemented
- [x] Schemas implemented
- [x] Lifespan and readiness isolation implemented
- [x] `/api/chat` implemented
- [x] Chat unit tests implemented
- [x] All tests passed
- [x] Data validation passed
- [x] Retrieval smoke test passed
- [x] Fake-provider chat smoke test passed
- [x] Real Groq smoke test passed or accurately blocked
- [x] Documentation updated
- [x] Protected-file review passed
- [x] Final diff reviewed

## Actions Taken

| Time | Phase | Action | Result |
|---|---|---|---|
| 2026-09-11 13:52 | Preflight | Ran branch, status, Python, full unittest discovery, key-presence, and Groq package checks | Passed. Branch is correct; working tree is clean; Python 3.11.9; all existing 24 tests passed; Groq SDK 1.7.0 installed; `GROQ_API_KEY` is absent. |
| 2026-09-11 13:52 | Repository state | Read latest commit | `29adf14 feat: add verified BIS retrieval API (#3)`. |
| 2026-09-11 13:53 | Separate SDK/key verification | Re-ran Groq package, key-presence, commit, and timestamp checks because the combined preflight output omitted its trailing checks | Passed. Groq is 1.7.0; key is absent; no key value was printed. |
| 2026-09-11 13:55 | Architecture/SDK inspection | Read the existing backend/tests and Groq 1.7.0 request types, completion types, and exceptions | Passed. SDK supports `response_format` with strict `json_schema`, `max_completion_tokens`, `temperature`, `tool_choice`, per-client timeout, optional string content, and typed authentication/timeout/rate-limit exceptions. |

| 2026-09-11 13:57 | Initial implementation | Added Groq pin, environment template/ignore exception, prompt, provider, chat service, schemas, independent generator lifespan state, and `/api/chat` | Completed without modifying retrieval or data components. |
| 2026-09-11 13:57 | Focused syntax check | Ran Python 3.11 `compileall backend` | Passed. |
| 2026-09-11 13:58 | Existing-test regression check | Ran full discovery before adding chat tests | Failed: 5 existing data-contract tests passed, but `test_api` could not import because new code imported `ContextManager` from the wrong Python 3.11 module. |
| 2026-09-11 13:59 | Import fix | Moved the `ContextManager` import from `collections.abc` to `typing` | Passed. All original 24 tests passed again. |
| 2026-09-11 14:03 | Chat unit tests | Added and ran 28 fake-provider/fake-Retriever tests | Passed 28/28 with no network, E5, real Chroma, data modification, or real key. |
| 2026-09-11 14:04 | Full syntax/test verification | Ran Python 3.11 compile and complete unittest discovery | Passed. All 52 tests passed: 24 existing plus 28 grounded-chat tests. |
| 2026-09-11 14:04 | Data validation | Ran `ingestion\validate_data.py` | Passed: 8 sources, 89 pages, 917 chunks. Protected data was not regenerated. |
| 2026-09-11 14:05 | Real local-server smoke | Started hidden Uvicorn PID 9012 on free port 8000 and tested the production app with the real Retriever | Health passed with count 917; retrieval returned five results with genuine source/page metadata; Swagger exposed all three endpoints; chat returned the expected safe 503 because Groq configuration is absent. |
| 2026-09-11 14:05 | Server cleanup | Verified PID 9012 executable/command, inspected logs, stopped only that PID, and removed task-created logs | Passed. No traceback or API-key-like text appeared; port process stopped cleanly. |
| 2026-09-11 14:07 | Documentation | Added grounded-chat configuration, request/response, citations, abstention, provider-error behavior, and legal-information disclaimer to README | Passed. No historical environment or data workflow was restored. |
| 2026-09-11 14:08 | Dependency/final verification | Ran `pip check`, Python 3.11 compile, all unit tests, and data validation | Passed: dependencies consistent, 52/52 tests, and 917 chunks validated. |
| 2026-09-11 14:08 | Git and credential audit | Ran status, branch, diff check/stat/name checks, staged/untracked checks, protected-path status, ignore checks, and credential-pattern search | Passed except a fake test sentinel resembled a Groq key prefix; no real credential was present. Protected and staged path checks were empty. |
| 2026-09-11 14:09 | Credential-hygiene cleanup | Replaced the fake `gsk_`-prefixed test sentinel with a provider-neutral marker | Passed; repository credential-pattern search returned no matches. |
| 2026-09-11 14:09 | Verification environment diagnosis | A sandboxed final rerun could not launch `venv311`; inspected the interpreter and base runtime paths | The runtime files were present. Direct access to the current-user Python directory was denied by the filesystem sandbox, so the environment was not renamed or rebuilt. |
| 2026-09-11 14:10 | Final required verification | Re-ran compile, all unit tests, and data validation with permission to access the installed current-user runtime | Passed: 52/52 tests and data validation for 8 sources, 89 pages, and 917 chunks. |
| 2026-09-11 14:10 | Final review | Confirmed no staged changes, no protected-path changes, no credential-like strings, and no modifications under retrieval, ingestion, raw data, generated data, or Chroma | Passed. `git diff --check` reported only informational Windows LF-to-CRLF working-copy warnings, not whitespace errors. |

## Files Created

- `docs/GROUNDED_CHAT_API_IMPLEMENTATION.md`
- `.env.example`
- `backend/prompts.py`
- `backend/generation.py`
- `backend/chat_service.py`
- `tests/test_chat_api.py`

## Files Modified

- `.gitignore`
- `requirements.txt`
- `backend/settings.py`
- `backend/schemas.py`
- `backend/main.py`
- `README.md`

## Commands Executed

- Git branch/status preflight — passed; correct branch and clean tree.
- `.\venv311\Scripts\python.exe --version` — passed; Python 3.11.9.
- Full pre-implementation unittest discovery — passed; 24/24 tests.
- `GROQ_API_KEY` presence check — absent; the value was never printed.
- `.\venv311\Scripts\python.exe -m pip show groq` — passed; version 1.7.0.
- Latest Git commit inspection — passed; commit `29adf14`.
- Separate Groq/key/commit/time checks — passed and confirmed the initial log fields.
- Existing backend/test and installed Groq source inspection — passed; structured-output and error-handling contracts confirmed locally.
- Focused backend compile — passed.
- First post-implementation unittest discovery — failed during `test_api` import due to the new `ContextManager` import.
- Existing-suite rerun after import fix — passed 24/24.
- Focused grounded-chat test discovery — passed 28/28.
- Full backend/tests compile and unittest discovery — passed 52/52.
- Data validator — passed; 8 sources, 89 pages, 917 chunks.
- Port check/server startup/health/retrieval/chat/Swagger smoke tests — real Retriever paths passed; chat correctly returned 503 for missing configuration.
- Server process/log cleanup — passed; only PID 9012 stopped and temporary logs removed.
- `pip check` — passed; no broken requirements.
- Final Git diff/status/protected/staged/credential audit — passed; no protected or staged paths and no credential-like strings.
- First final verification rerun inside the filesystem sandbox — failed to launch the venv because access to its current-user base runtime was denied.
- Final verification rerun with current-user runtime access — passed compile, all 52 tests, and validation of 917 chunks.

## Errors Encountered

| Error | Cause | Resolution | Verification |
|---|---|---|---|
| Real Groq smoke test unavailable | `GROQ_API_KEY` is not present in the process environment. | Continue with fake-provider unit and HTTP tests; do not request or store a key. | Real provider smoke test will remain blocked unless the environment changes. |
| `ImportError: cannot import name 'ContextManager' from 'collections.abc'` | Python 3.11 exposes the typing annotation through `typing`, not `collections.abc`. | Imported `ContextManager` from `typing`; kept `Mapping` from `collections.abc`. | Original suite passed 24/24 and chat suite passed 28/28. |
| Final venv commands initially reported `Unable to create process` | The managed filesystem sandbox denied access to the current-user Python 3.11 base installation used by `venv311`; the runtime itself remained present. | Re-ran the same read/build/test commands with permission to access that installed runtime; did not rename, delete, or recreate the venv. | Compile, 52 tests, and data validation all passed. |
| Credential-pattern audit matched a fake test sentinel | The fixture deliberately used a `gsk_` prefix while testing non-disclosure. It was not a real key. | Replaced it with a provider-neutral secret marker in `tests/test_chat_api.py`. | Credential-pattern search returned no matches; full 52-test suite passed. |

## Test Results

- Pre-implementation suite: 24/24 passed.
- Post-fix existing suite: 24/24 passed.
- Focused chat suite: 28/28 passed.
- Complete suite: 52/52 passed.
- Data validation: passed; 8 sources, 89 pages, 917 chunks.
- Real Groq smoke test: blocked by missing environment configuration.

## API Smoke Tests

- Health: HTTP 200, `ready`, collection count 917.
- Retrieval: HTTP 200, five results with source filenames and page ranges.
- Chat without key: HTTP 503 with `Chat generation is unavailable.` and no sensitive detail.
- Fake-provider chat: grounded, citation-validation, repair, abstention, timeout, rate-limit, and error paths passed in the 28-test suite.
- Swagger/OpenAPI: HTTP 200; `/health`, `/api/retrieve`, and `/api/chat` present.
- Real Groq generation: blocked because `GROQ_API_KEY` is absent.
- Server: PID 9012 verified and stopped; logs removed.

## Remaining Work

Provide `GROQ_API_KEY` through the process environment outside the repository, then rerun the two live `/api/chat` smoke requests (the grounded battery-operated-toy question and weak-evidence handmade-toy question). The key must not be written to the repository or this log. This is the sole remaining blocker to changing status to Completed.

## Final Summary

The grounded chat implementation is complete and reviewable. It uses the existing singleton Retriever, assigns backend-trusted evidence IDs, sends only the current question and exact retrieved evidence to one singleton Groq client, requires strict structured JSON, validates and deduplicates citations, maps citation metadata exclusively in the backend, retries malformed output once, and returns a safe abstention when evidence is absent or declared insufficient. All 52 offline tests pass, data validation passes for 917 chunks, and the real health/retrieval/Swagger smoke checks pass. Status is Blocked only because `GROQ_API_KEY` is absent, preventing the required live Groq generation smoke test.

## Grounding Remediation — 2026-09-11

### Observed failures and root causes

- The battery-operated-toy response listed IS 9873 parts as though they were the complete applicable standard. The prompt did not explicitly require the primary electric-toy standard to be distinguished from secondary requirements.
- The handmade-toy response converted a conditional artisan exception into a blanket exemption. The prompt did not prohibit extending a qualifying artisan rule to all handmade toys.
- The artisan citation displayed a chunk prefix/preamble rather than the claim-supporting text. Citation IDs were checked, but no model-supplied verbatim supporting span was required or validated.

### Files changed

- `backend/schemas.py`, `backend/prompts.py`, `backend/chat_service.py`, and `backend/generation.py`
- `retrieval/search.py`
- `tests/test_chat_api.py`
- `README.md` and this implementation log

### Safeguards added

- Strict structured citations are now `{citation_id, supporting_quote}`. Quotes must be 20–500 characters, nonempty, whitespace-normalized exact substrings of the matching trusted passage, and relevant to the question or answer. Backend-controlled filename, pages, and chunk ID remain authoritative.
- The API displays the validated supporting quote, not the beginning of a retrieved chunk. Unknown IDs, invented text, quotes from another ID, and preamble-only unrelated text trigger one repair attempt; a second failure returns safe insufficient evidence.
- The prompt now requires support for every material factual claim; preservation of qualifications, exceptions, scope, dates, and modal wording; qualified handling of incomplete/conflicting sources; no handmade-to-artisan inference; and primary/secondary-standard distinction.
- Universal-question answers that begin affirmatively require an explicit universal scope term in the cited quote.
- Retrieval retains vector ranking but logs a lexical-coverage tie-breaker for electric/battery/IS 15644/artisan/registered/handmade/exemption queries so definitions and qualifications are more likely to remain in the maximum eight chat passages. No dataset or embedding rebuild was performed.

### Tests added

- Deterministic fake-provider tests cover primary IS 15644 versus secondary IS 9873 labels, qualified artisan conditions, rejection of unconditional universal answers, verbatim excerpts, invented and wrong-ID quotes, preamble-only quotes, unknown IDs, and safe abstention after failed repair.

### Verification results and sanitized live outputs

- `PYTHONUTF8=1 .\\venv311\\Scripts\\python.exe -m unittest discover -s tests -v`: passed, 58 tests.
- `PYTHONUTF8=1 .\\venv311\\Scripts\\python.exe ingestion\\validate_data.py`: passed, 8 sources, 89 pages, and 917 chunks.
- A temporary local Uvicorn instance on port 8011 was started against the existing collection. `/health` returned `ready` with 917 chunks. Both requested `/api/chat` calls returned the safe HTTP 503 `Chat generation is unavailable.` because the process environment did not contain provider configuration; no secret was printed. The temporary process was stopped.
- Consequently, revised live generated answers could not be obtained in this session. The deterministic fake-provider cases verify the required acceptance behavior; rerun the two calls in a process environment that supplies the provider key without placing it in a file, log, or test.

## Provider Strict-Schema Diagnosis — 2026-09-11

### Change and likely root cause

The former full request sent `GenerationOutput.model_json_schema()` to Groq. That generated schema contains Pydantic validation keywords (including length limits and schema metadata) that are not necessary for Groq strict mode and can cause a `response_format` schema rejection. The provider request now uses a hand-authored minimal closed schema: root and citation objects forbid additional properties, all properties are required, and no Pydantic constraints, titles, defaults, formats, examples, references, or definitions are sent. Python retains all quote-length and semantic checks after generation.

### Safe diagnostics

Provider failures now log only exception class, HTTP status, Groq error type/code, request ID, and a sanitized/truncated message. Authorization values and `gsk_`-style values are redacted, and semicolon-appended request context is discarded. Prompts, retrieved passages, response bodies, and API keys are neither logged nor exposed in API responses. Authentication, rate-limit, bad-request, timeout, connection, internal-server, generic 5xx, and generic status failures are classified separately; 429 preserves `Retry-After`, while connection and 5xx failures map to the existing safe unavailable response.

### Tests and verification

- Added deterministic tests for recursively closed/required provider schema, required citation properties, absence of unsupported schema keywords, safe BadRequest classification/logging, and RateLimit classification. Existing quote-verbatim, quote-length, repair, and retrieval/chat coverage remain in place.
- Full unit discovery passed: 61 tests.
- Data validator passed: 8 sources, 89 pages, 917 chunks.

### Exact observed provider status/code

The original 502 did not record a status or error code, so an exact historical value cannot be recovered safely from the old generic log. A new minimal live request was attempted after adding diagnostics, but the current execution process has no provider configuration and stopped before any request was sent. It therefore produced no Groq status/code rather than a fabricated diagnosis. The next keyed full request will log the exact sanitized status/code and distinguish an expected 400 `response_format` rejection from context, rate-limit, or service failure.

## Completion-Budget Remediation — 2026-09-11

### Confirmed live root cause

The accepted strict schema is retained. The battery request failed with the provider diagnostic `BadRequestError`, HTTP `400`, error type `invalid_request_error`, code `json_validate_failed`: max completion tokens were reached before a valid document could be generated. This is a completion-budget failure, not an authentication, network, or schema-compatibility failure.

### Fix and bounded-attempt policy

- The default is now `GROQ_MAX_COMPLETION_TOKENS=2048`; values outside 256–4096 or non-integers safely fall back to 2048 during settings loading. The setting is documented in `.env.example`.
- GPT-OSS requests keep `max_completion_tokens`, `temperature=0`, strict JSON schema, `reasoning_effort="low"`, and `include_reasoning=false`; no unsupported `reasoning_format` is sent.
- Each chat request makes at most two provider calls. It performs either (a) an initial call plus one concise retry for precisely the 400/`json_validate_failed`/completion-exhaustion condition, or (b) an initial call plus one semantic-output repair. The paths cannot combine. A second completion exhaustion or invalid concise response returns safe insufficient evidence.
- The concise retry uses the same trusted evidence and schema, asks for under-120-word material answers, normally 1–3 citations, and the smallest complete quotes. It never removes legal qualifications solely for brevity.

### Logging and artisan review

- Diagnostics now remove `failed_generation` and its contents from messages, and never log its body field. A deterministic fixture confirms fake failed-generation/retrieved text is absent from logs.
- The complete artisan sentence crosses two adjacent English page-2 chunks. It continues after “Artisans” with: registration with the Office of the Development Commissioner (Handicrafts), under the Ministry of Textiles, Government of India. A handmade-toy answer must retain that registration, authority, manufacturer/seller, and goods/articles scope. The generated_v3 dataset was inspected only; no chunk-boundary defect was modified.

### Verification

- Full unit discovery passed: 68 tests.
- Data validation passed after this final documentation update: 8 sources, 89 pages, 917 chunks.
- No keyed live test was run from this Codex process. The implementation is ready for the user-run live test.

## Retrieval Coverage and Completeness Remediation — 2026-09-11

### Local Retriever diagnostic (no Groq call)

Only provenance and boolean term coverage are recorded below; document text was not logged. Flags are `15644`, `9873`, `artisan`, `registered`, and `commissioner`, respectively. `*` means the legal sentence is split with the immediately adjacent chunk on the same source page.

| Query | Rank: source/page/chunk-prefix | Flags |
|---|---|---|
| battery-operated toy | 1 product_manual_2026.pdf/4/d938f351 | – – – – – |
|  | 2 product_manual_2026.pdf/3/deb8982e | – Y – – – |
|  | 3–4 product_manual_2026.pdf/4/c09a2730,457fb83d | – – – – – |
|  | 5 product_manual_2026.pdf/6/29fd821c | Y Y – – – |
|  | 6 product_manual_2026.pdf/2/cc990c91 | Y Y – – – |
|  | 7–8 product_manual_2026.pdf/58,54/9135b996,29b13c08 | – – – – – |
| electric primary IS 15644 | 1 product_manual_2026.pdf/6/29fd821c | Y Y – – – |
|  | 2 product_manual_2026.pdf/2/cc990c91 | Y Y – – – |
|  | 3–8 product_manual_2026.pdf/2,3,58,54,58,54/e98983c3,deb8982e,9135b996,29b13c08,28bcb241,cf1e24d6 | – (rank 4/8 only) – – – |
| handmade exemption | 1 Second-Amendment-2020.pdf/2/b218d69b* | – – Y – – |
|  | 2–4 Toy_QC_order.pdf/3,3; product_manual_2026.pdf/4 | – – – – – |
|  | 5 Second-Amendment-2020.pdf/2/4b9c82fa* | – – – Y Y |
|  | 6–8 QCO-2024.pdf/2; product_manual_2026.pdf/9,1 | – – – – – |
| artisan registered commissioner | 1 Second-Amendment-2020.pdf/2/4b9c82fa* | – – – Y Y |
|  | 2 Second-Amendment-2020.pdf/2/b218d69b* | – – Y – – |
|  | 3 QCO-2024.pdf/2/78a1234b | – – – – – |
|  | 4 Second-Amendment-2020.pdf/2/c606a135 | – – – – – |
|  | 5–8 Toy_QC_order.pdf/2; transition notice/5; product manual/5; QCO-2024/2 | – – – – – |

### Root cause and safeguards

The failure was a combination of retrieval coverage, a page-2 chunk boundary, and generation/validator weakness. The original battery query did contain the primary-standard passages only at ranks 5–6, where they were vulnerable to a smaller final evidence set; the generator could then cite only secondary text. The original artisan query returned the start and continuation of the clause separately, allowing a partial quote to hide the registration condition.

- Chat retrieval now merges the original query with controlled coverage queries for electric/battery standards and artisan exemptions, deduplicates by chunk ID, deterministically reranks evidence content, and supplies at most eight passages.
- When a selected artisan clause is split, the Retriever safely loads its immediate same-page neighbour as a separate evidence item retaining that chunk’s stored ID and metadata. No quote is concatenated across chunks.
- Evidence-based validators require primary IS 15644 and secondary IS 9873 distinction when both are present, and reject a secondary-only answer. They require registered/Office of the Development Commissioner/Ministry of Textiles in both an artisan answer and its selected quotes when the complete clause is available; incomplete artisan evidence abstains.

### Tests and result

- Added deterministic tests for coverage merge/deduplication, retained primary-standard evidence, secondary-only repair, partial artisan-quote rejection, and abstention when complete qualification evidence is absent. Existing two-provider-call cap remains covered.
- Full unit discovery passed: 72 tests. Final data validation passed: 8 sources, 89 pages, 917 chunks.
- Expected live acceptance: the battery answer names IS 15644 as the primary electric-toy standard and labels cited IS 9873 requirements as secondary; the artisan answer begins “No,” and preserves manufactured-and-sold, registration, Office of the Development Commissioner (Handicrafts), and Ministry of Textiles conditions with verbatim supporting excerpts.

## Collective Citation Coverage and Over-Abstention Fix — 2026-09-11

The latest keyed responses abstained even though eight selected passages contained both halves of the relevant facts. The defect was not absence of evidence: repair output received only a generic invalid-response instruction, so it did not know that the missing legal condition lived under a separate trusted ID. Completeness checks must evaluate the collective citation set; no one quote or chunk is required to span the battery standards or the split artisan clause.

- Safe validation codes are now emitted internally: `MISSING_PRIMARY_STANDARD`, `MISSING_SECONDARY_CLASSIFICATION`, `MISSING_ARTISAN_SCOPE`, `MISSING_REGISTRATION_CONDITION`, `MISSING_AUTHORITY`, `INCOMPLETE_COLLECTIVE_EVIDENCE`, and `UNSUPPORTED_QUOTE`. Abstention logs contain only codes and trusted citation IDs, never answer text, prompt/evidence text, failed generations, or credentials.
- Repairs receive the code(s) plus role-to-ID hints (primary standard, secondary standard, artisan scope, registration condition). They are instructed to cite multiple IDs when facts are split; no expected answer text is injected.
- Collective output validation accepts separate verbatim quotes for the artisan manufacture/sale scope and its registration/office/ministry continuation, and likewise separate primary/secondary standard quotes. Every individual quote remains checked only against its own trusted passage.
- Added split-clause regression fixtures and tests for accepted collective citations, coded repair adding the second citation, and retained two-call provider cap. The latest focused regressions pass; final full-suite results are recorded after final verification.

## Backend-Controlled Citation Excerpts — 2026-09-11

### Diagnostic and root cause

The battery live failure was `UNSUPPORTED_QUOTE`: the model selected a trusted ID but its copied supporting quote failed the former exact-substring path before citations could be returned. This made Unicode/OCR punctuation and model paraphrase a false grounding failure. The artisan repair did receive all eight serialized evidence passages in both calls; its failure codes (`MISSING_REGISTRATION_CONDITION`, `MISSING_AUTHORITY`) show generation omission, not absent adjacent evidence or missing prompt serialization.

### Design

- Model `supporting_quote` is now a non-authoritative hint. The model still selects trusted citation IDs, but the backend derives a <=500-character verbatim line/clause from that exact trusted passage using question-sensitive evidence anchors.
- The API never displays model-copied text. Unicode is preserved exactly from stored source text. Unknown IDs and IDs without a relevant backend source span are rejected with precise internal codes (`UNKNOWN_CITATION_ID`, `QUOTE_NOT_RELEVANT`); collective completeness remains checked across the backend-selected excerpts.
- Repair calls receive the complete trusted evidence list again through the normal prompt plus safe codes, evidence IDs, and role mappings. No answer text or prompt/evidence content is logged in production; abstention logs contain codes and IDs only.

### Regression tests

- Added tests for Unicode punctuation preservation, paraphrased/wrong-ID model quote hints never being displayed, backend verbatim excerpts, split battery/artisan collective citation coverage, missing evidence abstention, and coded repair evidence-role feedback. Final verification passed: 75 tests; data validation passed with 8 sources, 89 pages, and 917 chunks.

## Extractive Fallback for Complete Evidence — 2026-09-11

The final live codes confirm a model-compliance failure: complete trusted evidence was present, but both model attempts omitted `MISSING_PRIMARY_STANDARD` or the artisan registration/authority conditions. The API now distinguishes genuine evidence insufficiency from failed model grounding.

- Before generation, the backend builds an evidence plan from trusted passages: primary/secondary standard roles or exemption scope/registration condition/registering authority roles, their IDs, and backend-derived excerpts.
- Normal strict-schema generation and its one bounded repair still run first. If both fail validation and the plan is complete, the API returns an evidence-driven extractive answer with trusted citations, `grounded=true`, `insufficient_evidence=false`, `generation_mode="extractive_fallback"`, and model `extractive-evidence-fallback`.
- Incomplete plans remain safe abstentions with `generation_mode="abstention"`; valid model answers report `generation_mode="llm"`.
- The fallback formatter contains only generic linking language. Standard numbers, legal scope, registration, authority, ministry, and excerpts are selected from indexed evidence at request time.
- Added extractive fallback regression coverage for separate battery primary/secondary chunks, two-call cap, nonempty trusted citations, and non-Groq fallback model identity. Final verification passed: 76 tests; data validation passed with 8 sources, 89 pages, and 917 chunks.
- Sanitized expected live battery shape: “For a battery-operated/electric toy, the primary standard is IS 15644…; cited IS 9873 parts are additional/secondary requirements.”
- Sanitized expected live handmade shape: “No, not all handmade toys are automatically exempt…,” followed only by the retrieved registration, manufacturer/seller, authority, and product-scope conditions. Each citation excerpt must be a verbatim supporting sentence, not a notification preamble.

## Normative Role Selection and Display Regression — 2026-09-11

The real-index tests were strengthened before production changes. The initial deterministic run failed as intended: battery had one citation (`1 not greater than or equal to 2`), while artisan output contained `government of\nindia:.`.

- Battery selection now excludes procedural test-report, “may also be considered”, and licence-grant passages. It reserves concise direct electric-toy/IS 15644 and applicable-secondary/IS 9873 table evidence within the final eight candidates.
- Secondary selection requires the Parts 2, 3, 4, 9, 10 and 11 sequence. The fallback expands that compact table notation into unambiguous part labels in the answer while retaining its selected source excerpt.
- Display formatting collapses PDF whitespace, removes prefixes and terminal artifacts, and prevents an excerpt boundary from preceding its anchor. Artisan fragments join grammatically instead of producing “subject to registered”.
- A rejected model candidate is now logged as `Model candidate rejected`, because complete-evidence fallback can follow.
- The strengthened real-index module passed (2 tests); full discovery passed (78 tests); data validation passed (8 sources, 89 pages, 917 chunks). No keyed live call, corpus change, or embedding rebuild occurred.

## Live Fallback Formatting and Real-Index Regression — 2026-09-11

### Observed failures and root causes

The live battery request abstained because the evidence-plan detector incorrectly required the word `primary` beside IS 15644, although the retrieved direct standard passage did not use that label. The artisan fallback duplicated a citation and exposed an index prefix plus a line-wrapped fragment ending in “Government of”. These were selection/formatting defects, not a missing-data defect.

### Safeguards added

- The evidence plan treats direct IS 15644 and IS 9873 matches as the primary and secondary standard roles respectively for an electric/battery toy question, and preserves the first reserved direct match rather than allowing a later topical passage to overwrite it.
- Retrieval reserves direct lexical role matches (`IS 15644`, `IS 9873`, artisan manufacture/sale scope, and Development Commissioner registration) before filling the eight final evidence positions. This change is logged here because it changes chat retrieval only; the generated_v3 dataset and embeddings were not modified.
- Model `supporting_quote` is again a required validation input: after whitespace normalization it must be 20–500 characters, occur verbatim in the selected trusted passage, and be related to the answer. Invented, wrong-ID, empty, and preamble-only quotes are rejected before the one repair attempt.
- The displayed excerpt remains backend-selected from its trusted passage, strips only an extraction prefix, grows through same-passage wrapped lines to a punctuation boundary, rejects dangling fragments, and deduplicates citations by trusted chunk ID.

### Tests and verification

- Updated fake-provider tests now assert rejection of invented and wrong-evidence-ID quotes rather than silently replacing them. The suite also covers the conditional artisan scope, unknown IDs, preamble-only claims, repair abstention, primary/secondary labelling, and verbatim excerpts.
- Added `tests/test_real_data_integration.py`, which runs against the existing local index with an invalid fake generator so that the evidence-driven fallback is deterministic. It verifies both real battery roles and the real artisan scope/registration/authority roles, no duplicate chunks, no index prefix, and no dangling “Government of” excerpt.
- Required full discovery passed: 78 tests (including the 2 real-index integration tests). Data validation passed: 8 sources, 89 pages, 917 chunks. No Groq key was used.
- Sanitized integration battery output contains “Primary/applicable standard” with IS 15644 and “Secondary/additional requirements” with IS 9873. Sanitized integration artisan output does not begin “Yes” and contains only the retrieved manufacture/sale, registration, Development Commissioner, and Ministry of Textiles conditions.
