# Candidate-backed response safety

Provider-disabled `ChatService` was constructed with the real local `LocalChromaRetriever` pointed only at `bis_corpus_v4_candidate_01346f7d11f1`.

- 28/28 cases passed across toy, FMCS, jewellery, helmet, laboratory, fee, vague, unrelated, greeting, acknowledgement, and Hindi/Marathi/Tamil/Bengali inputs.
- Published citations had source filename, page, chunk ID, and valid section citation references. No historical source, prompt-injection phrase, secret marker, or blank OCR-form field reached answer prose.
- Currentness-sensitive or unsupported requests returned safe clarification or limitation paths. Existing fake-provider backend tests covered malformed output, stronger modality, invented assertions, and provider failure fallback.
