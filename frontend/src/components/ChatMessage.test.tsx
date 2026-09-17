import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { ChatMessage } from './ChatMessage';

const response = {
  answer: 'A grounded answer.', grounded: true, insufficient_evidence: false, evidence_count: 2,
  citations: [
    { citation_id: 'S1', source_filename: 'a very long trusted source filename.pdf', page_start: 4, page_end: 4, chunk_id: 'one', excerpt: 'Normal source wording.' },
    { citation_id: 'S2', source_filename: 'second.pdf', page_start: 5, page_end: 6, chunk_id: 'two', excerpt: 'Table 1 | Column 2' },
    { citation_id: 'S2', source_filename: 'second.pdf', page_start: 5, page_end: 6, chunk_id: 'two', excerpt: 'Table 1 | Column 2' },
  ], model: 'test', generation_mode: 'llm' as const, disclaimer: 'Verify.',
};

it('renders a source heading, count, distinct citation cards, and page range', () => {
  render(<ChatMessage role="assistant" text={response.answer} response={response} />);
  expect(screen.getByRole('heading', { name: /sources 2/i })).toBeInTheDocument();
  expect(document.querySelectorAll('.citation-card')).toHaveLength(2);
  expect(screen.getByText('Pages 5–6')).toBeInTheDocument();
  expect(screen.getByText('a very long trusted source filename.pdf')).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent('one');
  expect(document.body).not.toHaveTextContent('two');
  expect(screen.queryByText('Technical details')).toBeNull();
});

it('presents guided sections before the trusted sources', () => {
  render(<ChatMessage role="assistant" text="Legacy answer" response={{ ...response, answer_sections: [
    { type: 'direct_answer', title: 'Direct answer', content: 'IS 15644 is primary.', items: [], citation_ids: ['S1'] },
    { type: 'next_steps', title: 'What you should do', content: null, items: ['Check the applicable standard.'], citation_ids: ['S1'] },
  ] }} />);
  expect(screen.getByRole('heading', { name: 'Direct answer' })).toBeInTheDocument();
  expect(screen.getByText('Check the applicable standard.')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: /sources 2/i })).toBeInTheDocument();
});

it('groups a compliance journey once per category without losing distinct backend sections', () => {
  const journeyResponse = { ...response, answer_sections: [
    { type: 'direct_answer' as const, title: 'Primary standard', content: 'IS 15644 is primary.', items: [], citation_ids: ['S1'] },
    { type: 'direct_answer' as const, title: 'Secondary standard', content: 'IS 9873 may apply.', items: [], citation_ids: ['S2'] },
    { type: 'direct_answer' as const, title: 'Primary standard', content: 'IS 15644 is primary.', items: [], citation_ids: ['S1'] },
    { type: 'explanation' as const, title: 'Why it applies', content: 'The cited material covers electric toys.', items: [], citation_ids: ['S1'] },
    { type: 'explanation' as const, title: 'Where this fits in your journey', content: 'This is user-provided context, not BIS evidence.', items: [], citation_ids: [] },
    { type: 'next_steps' as const, title: 'Preparation steps', content: 'Keep this subsection separate.', items: ['First checklist item.'], citation_ids: ['S1'] },
    { type: 'next_steps' as const, title: 'Documents to prepare', content: null, items: ['Second checklist item.'], citation_ids: ['S2'] },
    { type: 'next_steps' as const, title: 'Your next action', content: null, items: ['Open the cited primary standard.'], citation_ids: ['S1'] },
    { type: 'important' as const, title: 'Important condition', content: 'Evidence is limited to the cited material.', items: [], citation_ids: ['S1'] },
    { type: 'important' as const, title: 'Another condition', content: 'Verify before relying on this guidance.', items: [], citation_ids: ['S2'] },
  ] };
  render(<ChatMessage role="assistant" text={journeyResponse.answer} response={journeyResponse} presentation="compliance-journey" />);
  for (const heading of ['Applicable standards', 'Why these standards apply', 'Your compliance checklist', 'Important conditions', 'Recommended next action']) expect(screen.getAllByRole('heading', { name: heading })).toHaveLength(1);
  expect(screen.getAllByRole('heading', { name: /Verified sources 2/i })).toHaveLength(1);
  expect(screen.getAllByText('IS 15644 is primary.')).toHaveLength(1);
  for (const text of ['IS 9873 may apply.', 'The cited material covers electric toys.', 'This is user-provided context, not BIS evidence.', 'Preparation steps', 'Documents to prepare', 'First checklist item.', 'Second checklist item.', 'Open the cited primary standard.', 'Evidence is limited to the cited material.', 'Verify before relying on this guidance.']) expect(screen.getByText(text)).toBeInTheDocument();
  expect(document.querySelector('.journey-next-action')).toHaveTextContent('Open the cited primary standard.');
  expect(document.querySelector('.journey-checklist')).toHaveTextContent('Preparation steps');
  expect(document.querySelector('.journey-checklist')).toHaveTextContent('Documents to prepare');
  expect(screen.getByRole('link', { name: 'Page 4' })).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: /View evidence/i })).toHaveLength(2);
});

it('renders typed accessible suggested actions and submits one once', async () => {
  const action = vi.fn();
  render(<ChatMessage role="assistant" text="Choose" response={{
    ...response,
    suggested_replies: ['Non-electric', '<b>Battery</b>'],
  }} suggestedActions={[{ kind: 'chat_question', label: 'Non-electric', question: 'Non-electric' }, { kind: 'chat_question', label: '<b>Battery</b>', question: '<b>Battery</b>' }]} onSuggestedAction={action} />);
  expect(screen.getByRole('group', { name: 'Suggested replies' })).toBeInTheDocument();
  expect(document.querySelector('.suggested-replies b')).toBeNull();
  await userEvent.setup().click(screen.getByRole('button', { name: 'Non-electric' }));
  expect(action).toHaveBeenCalledTimes(1);
  expect(action).toHaveBeenCalledWith({ kind: 'chat_question', label: 'Non-electric', question: 'Non-electric' });
});
