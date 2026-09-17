import { expect, it } from 'vitest';
import { builtInSuggestedActions, normalizeSuggestedActions, questionForSuggestedAction } from './suggestedActions';
import type { ChatResponse } from './types/chat';

const response = (suggested_replies: string[], overrides: Partial<ChatResponse> = {}): ChatResponse => ({
  answer: 'Grounded answer.', grounded: true, insufficient_evidence: false, needs_clarification: false,
  evidence_count: 1, citations: [], model: 'test', generation_mode: 'extractive_fallback', disclaimer: 'Verify.', suggested_replies, ...overrides,
});

it('keeps every built-in suggestion in the explicit typed-action contract', () => {
  expect(builtInSuggestedActions).toHaveLength(4);
  for (const action of builtInSuggestedActions) {
    expect(action.kind).toBe('chat_question');
    if (action.kind === 'chat_question') expect(questionForSuggestedAction(action)).toBe(action.question);
  }
});

it('normalizes trusted standard, contextual, comparison, and roadmap suggestions without raw-label fallback', () => {
  const actions = normalizeSuggestedActions(response([
    'IS 15644', 'Explain when this standard applies', 'Explain this in simpler language',
    'Compare it with IS 9873 Part 1', 'Show my complete compliance roadmap', 'Tell me more',
  ], {
    needs_clarification: true,
    assistant_context: { expected_slots: ['standard_reference'], referenced_standards: ['IS 15644'] },
  }));
  expect(actions).toEqual([
    { kind: 'standard_explanation', label: 'IS 15644', standard: 'IS 15644' },
    { kind: 'chat_question', label: 'Explain when this standard applies', question: 'Explain when IS 15644 applies.' },
    { kind: 'standard_explanation', label: 'Explain this in simpler language', standard: 'IS 15644' },
    { kind: 'chat_question', label: 'Compare it with IS 9873 Part 1', question: 'Compare IS 15644 with IS 9873 Part 1.' },
    { kind: 'open_compliance_wizard', label: 'Show my complete compliance roadmap' },
  ]);
  expect(questionForSuggestedAction(actions[0])).toBe('Explain IS 15644 in simple words.');
  expect(actions.find((action) => action.label === 'Tell me more')).toBeUndefined();
});

it('does not transform unreferenced standards or unknown unsafe legacy labels', () => {
  const actions = normalizeSuggestedActions(response(['IS 99999', 'Explain this'], {
    needs_clarification: true,
    assistant_context: { expected_slots: ['standard_reference'], referenced_standards: ['IS 15644'] },
  }));
  expect(actions).toEqual([]);
});

it('keeps controlled clarification choices and self-contained questions explicit', () => {
  expect(normalizeSuggestedActions(response(['Mains-powered'], {
    needs_clarification: true, assistant_context: { expected_slots: ['power_type'] },
  }))).toEqual([{ kind: 'chat_question', label: 'Mains-powered', question: 'Mains-powered' }]);
  expect(normalizeSuggestedActions(response(['What documents are required?']))).toEqual([
    { kind: 'chat_question', label: 'What documents are required?', question: 'What documents are required?' },
  ]);
});
