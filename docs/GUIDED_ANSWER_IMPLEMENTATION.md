# Guided grounded answers

## Architecture

- `ChatRequest.audience` accepts `general` (the backward-compatible default), `manufacturer`, or `consumer`.
- Retrieval and citations remain backend-controlled. The chat service now converts selected evidence roles into an internal `FactPlan` containing stable fact IDs, statements, qualifications, and evidence IDs.
- `AnswerSection` adds a safe presentation contract while preserving the existing plain-text `answer` field. Sections contain only backend-composed text and backend-selected citation IDs.
- Complete role plans use a readable trusted composer. This avoids leaking table records when a provider is unavailable or malformed. Incomplete plans retain safe abstention or clarification behavior.

## Safeguards

- The model never controls source metadata, facts, legal qualifiers, dates, standard numbers, or citations.
- Returned sections are checked against selected citations and the fact plan. Unknown citation IDs and unsupported modal language are rejected.
- The manufacturer checklist is explicitly partial. The ambiguous-QCO response asks for the particular order and never invents a date. Transition permission remains conditional.
- Retrieved text is evidence, never instructions. User-visible output does not expose evidence roles or validation codes.

## Presentation

- The frontend uses direct-answer, explanation, next-step, condition, and clarification sections, then retains the existing trusted source cards.
- The audience selector changes wording and supported next actions only; it does not alter legal facts.

## Verification status

- Frontend and backend tests should be run using the commands in the task request. This host currently has a broken project Python launcher (`venv311` references a missing Python 3.11 executable), so backend commands cannot execute until that environment is repaired without changing repository content.
