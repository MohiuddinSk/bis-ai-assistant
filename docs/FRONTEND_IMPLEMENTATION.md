# Frontend implementation log

## 2026-09-12 — Grounded-answer presentation follow-up

- No frontend response contract or HTML rendering change was required. Deterministic backend composition now sends clean plain-text answers while citation cards retain traceable backend-controlled excerpts.
- The former 30–39 second live abstentions are expected to return immediately once complete trusted evidence roles are selected, because the backend bypasses provider generation for those plans.

## 2026-09-12 — Composition spacing correction

- No frontend renderer change was required. Backend deterministic fragments now preserve word boundaries and one-space joins before the plain-text answer reaches the UI.

## 2026-09-12 — Source citation visual repair

- The secure PDF viewer feature remained intact, but its new CitationCard class names initially had no corresponding visual system in the compressed legacy stylesheet. This produced unstyled white rectangles and browser-default PDF links.
- Rebuilt the citation styles around readable CSS tokens and semantic controls. Cards now have a subordinate Sources heading/count, source badge, page pill, readable filename wrapping, aligned evidence/PDF actions, visible keyboard focus, a labelled expanded-evidence panel, mobile-safe full-width controls, and reduced-motion support.
- The assistant answer is still rendered as one safe plain-text node. The deterministic answer composer, rather than the frontend, owns sentence spacing; the regression coverage now explicitly preserves `IS 15644. IS 9873`.
- Final stage frontend verification passed: lint, build, and verbose Vitest (4 files / 29 tests), with no React effect, `act(...)`, unhandled-promise, or unexpected-console warnings. Browser inspection at the desktop viewport found a visible non-zero application shell and no horizontal overflow. Provider-backed live submission was deliberately not run because no provider-key authorization was established for this process.

## 2026-09-11 — Stage: chat timeout repair and final frontend verification

- The blank-screen repair was verified again in a real browser: the rendered accessibility tree contains the application title, welcome content, suggested questions, input, status indicator, and footer. The error boundary did not render. The local Vite instance reported `Backend ready`.
- The new live symptom was a premature chat timeout while `/health` was ready. The client previously had one short request deadline; a successful health check therefore did not establish that the potentially much slower grounded-chat request could complete within that deadline. The client now has deliberately separate limits: health checks use 8,000 ms and chat uses 90,000 ms by default.
- `VITE_CHAT_TIMEOUT_MS` is a public, validated frontend-only setting. Values outside 1,000–300,000 ms or non-numeric values safely use the 90,000 ms default. `frontend/.env.example` documents it and contains no backend credentials.
- Each request creates its own AbortController and clears its timer in `finally`. An external health-check abort is reported as cancellation internally and ignored by the unmounted health effect; a deadline abort alone is labelled as a timeout. A retry calls the client again, creating a fresh controller.
- The waiting UI remains visible with the message “Searching BIS documents and validating citations…”, duplicate submission stays disabled, and the retained question can be retried after an error. HTTP 5xx/provider failures retain their service-unavailable message rather than being mislabelled as frontend timeouts.
- Added `frontend/src/services/api.test.ts` with deterministic controlled-Promise/fake-timer coverage for the former 30-second boundary, chat and health deadlines, fresh retry controllers, successful responses, HTTP provider errors, invalid configuration, and timer cleanup. Together with `App.test.tsx`, the suite is now 2 test files / 24 individual tests. It completed with no act, effect-lifecycle, unhandled-promise, or unexpected-console warnings.
- Added a local generic SVG favicon and linked it from `frontend/index.html`; it makes no BIS branding claim and removes the `/favicon.ico` request path.
- Live Vite-proxied API verification measured the battery question at 20.37 seconds and the artisan question at 5.07 seconds. Both returned structured grounded responses before the new 90-second deadline. Battery: “Primary/applicable standard: … Electric Toys … IS 15644. Secondary/additional requirements: … IS 9873 Part 2, Part 3, Part 4, Part 9, Part 10, and Part 11.” Its displayed excerpts were the applicable-standard `IS 15644` table row and the applicable-secondary IS 9873 table passage. Artisan: “No automatic blanket exemption is established. … [it] applies to goods or articles manufactured and sold by Artisans registered with Office of the Development Commissioner (Handicrafts), under Ministry of Textiles, Government of India.” Its excerpts directly supported scope/sale and registration/authority respectively. Automated tests use no provider request or credentials.
- Verification: `npm run lint` passed; `npm run test -- --run --reporter=verbose` passed (2 files, 24 tests); `npm run build` passed (Vite 8.3.0). Backend regression then passed (78 tests) and `ingestion/validate_data.py` passed (8 sources, 89 pages, 917 chunks).

## 2026-09-11 — Stage: StrictMode blank-page and test-warning repair

- Real browser reproduced a blank page despite loaded CSS and health requests. Console identified the cause: an effect returned a Promise, so StrictMode attempted Promise cleanup and raised `destroy is not a function`.
- Replaced the health lifecycle with a synchronous effect that starts an internal async operation, uses an AbortController cleanup, and avoids state updates after abort/unmount. Health calls now occur only on StrictMode's initial mount cycle, not in a loop.
- Preserved `AppErrorBoundary` in `main.tsx` as a permanent startup safeguard.
- Fixed act-warning fixture behavior by awaiting health settlement, using Testing Library cleanup after every test, restoring mocks, and resolving deferred chat promises inside awaited `act` blocks.
- Frontend verification: lint passed; verbose Vitest passed (1 file, 16 tests) with no act/useEffect/unhandled-promise warnings; build passed.

## 2026-09-11 — Stage: behavioral-test expansion

- Audit confirmed the prior result meant **1 test file / 3 individual tests**, not three files.
- Expanded `frontend/src/App.test.tsx` to **1 test file / 16 individual deterministic behavioral tests**: welcome, suggestions, empty input, citation expansion, insufficient evidence, extractive fallback, loading, duplicate prevention, retry, Enter, Shift+Enter, ready/degraded/unavailable health, malformed API response, and raw-HTML-safe rendering.
- Added a minimal runtime chat-shape check so malformed success JSON reaches the friendly error state rather than being rendered as an answer.
- Verification: `npm run lint` passed; `npm run test -- --run --reporter=verbose` passed (1 file, 16 tests); `npm run build` passed. Vitest emitted non-failing React `act(...)` warnings for asynchronous health/loading fixtures.

## 2026-09-11 — Stage: verification complete

- Installed the declared frontend dependencies; Node emitted non-blocking engine warnings from jsdom/undici.
- Resolved Vite/Vitest type declarations, jsdom `scrollIntoView`, and a nested citation-button test assertion.
- `npm run lint` passed; `npm run test -- --run` passed (3 mocked tests); `npm run build` passed.
- Updated root/frontend setup documentation. Remaining: preserved backend and corpus verification; no keyed test will run from this task.

## 2026-09-11 — Stage: preserved backend verification

- Backend discovery passed: 78 tests. Dataset validation passed: 8 sources, 89 pages, 917 chunks.
- Added ignore rules for generated frontend `node_modules/` and `dist/`; no source, data, embeddings, or ChromaDB files were changed.
- Manual smoke test remains user-operated because it requires the user-configured provider environment. Exact commands are in the final report.

## 2026-09-11 — Stage: foundation and chat MVP

- Confirmed `feature/frontend-chat` and a clean worktree before editing.
- Replaced the frontend placeholder with a React/Vite/TypeScript application, typed API service, responsive CSS, and componentized chat UI.
- Used only `VITE_API_BASE_URL` in the example environment file; no credentials were created or stored.
- The client fixes `top_k` at 8, uses an AbortController timeout, handles HTTP/network/malformed JSON errors with friendly text, and never injects answer HTML.
- Added initial mocked API tests and frontend documentation. Remaining work: install dependencies, run frontend checks, then run backend regressions and record results.
