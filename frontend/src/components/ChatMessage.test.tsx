import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
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
