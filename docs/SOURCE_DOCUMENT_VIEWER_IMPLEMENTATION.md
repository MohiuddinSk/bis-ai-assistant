# Source document viewer implementation

## Stage 1 — registry and route

- Confirmed branch `feature/source-document-viewer` and inspected `generated_v3/source_registry.json` read-only.
- Added `GET /api/documents/{source_filename}`. It resolves only exact registered PDF basenames under repository-root-relative `data/raw`.
- Rejects decoded/double-encoded traversal, separators, Windows paths, absolute paths, unknown names, non-PDF names, and missing files with the same non-sensitive 404 response.
- Uses streamed `FileResponse` with inline PDF disposition, `nosniff`, and private/no-cache headers. No source path is included in responses.

## Stage 2 — citation UI

- Citation cards show source ID, filename, page/range, expandable evidence, and an encoded `Open source PDF` link. Page numbers are browser-only `#page=` fragments.
- Links open in a separate protected tab; absent filenames produce no link. Table-shaped excerpts are labelled `Extracted source text`.

## Tests and limitations

- Added registry security tests and citation-card URL/markup tests. No raw PDF, registry, embeddings, or Chroma data was modified.
- PDF page fragments depend on the browser's PDF viewer; the backend never interprets a page number as a filesystem path.
- Verification: frontend lint/test/build passed (26 tests); backend discovery passed (85 tests); data validation passed (8 sources, 89 pages, 917 chunks); retrieval regression passed (10/10). A non-keyed route smoke check returned `200 application/pdf`, inline disposition, `nosniff`, and `404` for encoded traversal.

## Stage 3 — citation visual and accessibility repair

- Live source cards had regressed because the new `CitationCard` markup used `citation-card`, `citation-actions`, and related class names while the compact legacy stylesheet only styled the former generic citation markup. The browser therefore exposed default anchor styling and weak content hierarchy.
- Replaced the compressed stylesheet with readable token-based CSS and added matching card styles: a restrained saffron accent outside the text flow, neutral card background, source badge, page pill, distinct card gap, aligned action controls, focus states, responsive mobile controls, and reduced-motion support.
- `ChatMessage` now provides a visually subordinate `Sources (n)` section. Expanded panels are labelled `Extracted source text`, remain plain text, and are linked to their toggle with `aria-controls` / `aria-expanded`.
- The visible `IS 15644.IS 9873` issue is not caused by JSX or CSS: the renderer displays the answer as one plain-text node and the deterministic composer already joins these fragments with a space. A real-index regression now asserts the correct boundary (`IS 15644. IS 9873`) and rejects the joined form.
- Added semantic tests for the source badge, page, descriptive protected PDF link, evidence relationship/toggle state, source count, missing filenames, raw HTML as text, and answer sentence spacing. No raw PDF, registry, embeddings, Chroma data, or credentials were changed.
- Verification for this stage: frontend `npm run lint`, verbose Vitest, and production build passed; Vitest reports 4 files / 29 tests with no React warnings. A real browser at `http://127.0.0.1:5174/` showed the visible application shell, expected accessibility tree, non-zero `#root` / `main` dimensions, and no horizontal overflow at its desktop viewport. Provider-backed chat was intentionally not submitted because the current browser/backend environment may hold a provider key.
- The requested Python verification commands could not run in this host: the checked-in `venv311` launcher references a removed Python 3.11 executable and the system Python launcher reports no installed Python. This is an environment repair item, not a test result or source change.
