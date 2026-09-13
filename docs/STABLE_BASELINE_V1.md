# BIS Saarthi Stable Baseline V1

## Baseline identity

- **Baseline source commit:** `ab47dc4c70788f1cc31044fbe25f09689fc2e554`
- **Source branch:** `main`
- **Intended release tag:** `prototype-v1.0.0`
- **Verification date:** 2026-09-13
- **Project:** BIS Saarthi
- **SIH problem statement:** SIH26107
- **Team:** Vector Vibe

## Verified capabilities

- Natural-language BIS toy-compliance questions, personalized clarification questions, and bounded follow-up context.
- Seven-step Compliance Wizard and a complete compliance-roadmap option.
- Battery-operated, mains-electric, and non-electric routing.
- Applicable-standard identification for the supported toy corpus, plus explanation and comparison of supported Indian Standards.
- Grounded answer sections; citation and page metadata; evidence expansion; and source-PDF links.
- Safe handling of unknown standards and abstention for unsupported evidence.
- Protection against unsupported model-authored citations; internal chunk identifiers are hidden from users.

## Verified corpus

- **Sources:** 8
- **Pages:** 89
- **Chunks:** 917
- **Current domain:** BIS toy-compliance material

The corpus is not representative of the complete BIS standards and services collection.

## Verification results

- Backend unittest suite: 180 passed.
- Frontend Vitest suite: 50 passed across 5 files.
- Data validation: passed.
- Retrieval regression: 10/10 passed.
- Frontend TypeScript lint/typecheck: passed.
- Frontend production build: passed.
- `npm audit` during `npm ci`: 0 vulnerabilities.
- `git diff --check`: passed.

## Current architecture

- **Frontend:** React, TypeScript, and Vite.
- **Backend:** FastAPI and Pydantic.
- **Retrieval database:** ChromaDB.
- **Embedding model:** `intfloat/multilingual-e5-small`.
- **Retrieval:** dense vector similarity with lexical-coverage reranking.
- **Generation provider:** Groq through the existing generator interface.
- **Grounding:** backend evidence planning, citation validation, and safe abstention.
- **Demo frontend:** Netlify.
- **Demo backend exposure:** local FastAPI through a Cloudflare Quick Tunnel.

## Known limitations

- The indexed corpus is a narrow toy-compliance demonstration, not thousands of BIS standards.
- Hallmarking guidance and testing-laboratory discovery are not implemented.
- Full multilingual interaction and consumer-service coverage are incomplete.
- Certification-procedure coverage is partial: the indexed material does not establish every form, fee, laboratory, timeline, or step.
- Citations are page-backed but not universally clause-level.
- ChromaDB and the external model provider are suitable for the prototype, but are not approved as the final government deployment architecture.
- The backend depends on a locally running machine and Cloudflare Quick Tunnel.
- The system is not formally integrated with BIS authentication, APIs, portal technology, or NIC/MeghRaj infrastructure.
- Node.js 22.18.0 produced engine warnings because current `jsdom` and `undici` packages request a newer compatible Node version; all frontend checks still passed.
- Existing Starlette/httpx and ChromaDB/Pydantic deprecation warnings remain for dependency maintenance.

## Safety boundaries

- User-profile information is untrusted and is not BIS evidence.
- Unknown or unsupported standards do not receive substituted citations.
- The assistant does not guarantee certification outcomes and must not invent fees, forms, laboratories, timelines, clauses, or legal requirements.
- Guidance is informational and must be verified with BIS or a qualified professional.

## Reproduction commands

Run these verified commands from the repository root in Windows PowerShell. The frontend commands enter and leave `frontend` explicitly.

```powershell
# 1. Backend unittest discovery
.\venv311\Scripts\python.exe -m unittest discover -s tests -v

# 2. Data validation
.\venv311\Scripts\python.exe ingestion\validate_data.py

# 3. Retrieval regression
.\venv311\Scripts\python.exe retrieval\test_retrieval.py

# 4. Frontend dependency installation
Push-Location frontend
npm ci

# 5. Frontend lint/typecheck
npm run lint

# 6. Frontend tests
npm run test -- --run

# 7. Frontend production build
npm run build
Pop-Location

# 8. Git whitespace validation
git diff --check
```

## Rollback procedure

To inspect or perform emergency verification of the baseline:

```powershell
git fetch origin --tags
git switch --detach prototype-v1.0.0
```

Detached mode is for inspection or emergency verification. For development from the baseline, create a recovery branch:

```powershell
git switch -c recovery/from-prototype-v1 prototype-v1.0.0
```

## Next architectural priorities

1. BIS integration-readiness documentation
2. Versioned API contract
3. Dockerized backend
4. Provider-independent model gateway
5. Retrieval abstraction
6. Security and audit identifiers
7. Permanent backend deployment
8. Authoritative source registry
9. Retrieval evaluation and hybrid search
10. Expansion to additional BIS services
