# Manufacturer Compliance Wizard implementation

## Purpose and flow

The wizard helps users describe a toy without knowing BIS terminology. It keeps free-form chat available and collects role, product description, power, age group, guidance goal, and application stage across seven accessible steps. A review screen optionally accepts extra context before generation.

## API contract

`POST /api/compliance/guide` accepts the strict `ComplianceProfile` schema and returns `{profile, guidance}`. All enum values are closed, extra properties are rejected, the trimmed product description is 2–300 characters, and optional context is at most 500 characters.

Example:

```json
{"role":"manufacturer","product_description":"Battery-operated toy car","power_type":"battery_operated","intended_age_group":"3_to_8","goal":"identify_standards","application_stage":"researching","additional_context":null}
```

The response profile is normalized and `guidance` is the existing `ChatResponse`, including guided sections, safe status, trusted citations, disclaimer, and PDF links.

## Grounding and threat boundary

`compliance_query()` labels every profile as `UNTRUSTED USER CONTEXT` and says it is retrieval context, not legal evidence. It never assigns a standard, exemption, age rule, or legal conclusion. Product text and optional context are not logged. The endpoint calls the production chat handler, reusing the singleton retriever/provider, locks, fact plan, qualification and citation validation, repair limits, source mapping, and abstention behavior. There is no weaker wizard generation path.

Prompt-like profile text cannot change system instructions. Artisan selection cannot establish eligibility, and age/power selections only help retrieval. Legal claims still require indexed evidence.

## Frontend

The semantic wizard uses fieldsets, legends, labels, an announced progress indicator, inline description validation, Previous/Next/Generate/Retry/Start over controls, and preserves values while navigating. Requests have duplicate protection, the existing bounded timeout, and an AbortController that is cancelled on unmount. No local or session storage is used. Successful guidance is rendered through `ChatMessage` and `CitationCard`, so section structure, citation deduplication, evidence expansion, encoded PDF URLs, and safe text rendering remain shared.

## Tests and verification

Backend contract tests cover validation, normalization, audience mapping, neutral context, prompt-like input, sanitized failures, and unchanged core routes. Frontend tests cover seven-step navigation, progress, retention, validation, Not sure options, exact payload, loading, retry, reset, unmount abort, safe text, guided sections, citations, and source links.

Run:

```powershell
$env:PYTHONUTF8 = "1"
.\venv311\Scripts\python.exe -m unittest discover -s tests -v
.\venv311\Scripts\python.exe ingestion\validate_data.py
.\venv311\Scripts\python.exe retrieval\test_retrieval.py
cd frontend
npm run lint
npm run test -- --run --reporter=verbose
npm run build
```

## Local smoke test

```powershell
.\venv311\Scripts\python.exe -m uvicorn backend.main:app --reload
$body = @{role='manufacturer';product_description='Battery-operated toy car';power_type='battery_operated';intended_age_group='3_to_8';goal='identify_standards';application_stage='researching';additional_context=$null} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/compliance/guide -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 10
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`, choose **Compliance Wizard**, complete the steps, expand a citation, and open its registered PDF.

## Limitations

The wizard only covers evidence indexed in the local BIS toy corpus. It cannot establish that a checklist is complete, decide artisan eligibility, or invent fees, laboratories, dates, or procedures. Ambiguous or unsupported profiles must produce qualified guidance, clarification, or safe insufficiency.
