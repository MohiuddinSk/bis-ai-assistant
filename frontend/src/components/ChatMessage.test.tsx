import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { ChatMessage } from './ChatMessage';
import { LanguageProvider } from '../i18n/LanguageContext';
import { translations } from '../i18n/translations';

const response = {
  answer: 'A grounded answer.', grounded: true, insufficient_evidence: false, evidence_count: 2,
  citations: [
    { citation_id: 'S1', source_filename: 'a very long trusted source filename.pdf', page_start: 4, page_end: 4, chunk_id: 'one', excerpt: 'Normal source wording.' },
    { citation_id: 'S2', source_filename: 'second.pdf', page_start: 5, page_end: 6, chunk_id: 'two', excerpt: 'Table 1 | Column 2' },
    { citation_id: 'S2', source_filename: 'second.pdf', page_start: 5, page_end: 6, chunk_id: 'two', excerpt: 'Table 1 | Column 2' },
  ], model: 'test', generation_mode: 'llm' as const, disclaimer: 'Verify.',
};

it('renders a greeting as guidance without a grounded or insufficient badge', () => {
  render(<ChatMessage role="assistant" text="Hello, I am BIS Saarthi." response={{
    answer: 'Hello, I am BIS Saarthi.', grounded: false, insufficient_evidence: false, evidence_count: 0,
    citations: [], model: 'local', generation_mode: 'conversation', disclaimer: 'Verify.',
    answer_sections: [{ type: 'direct_answer', title: 'BIS Saarthi', content: 'Hello, I am BIS Saarthi. This prototype covers toy-related BIS material.', items: [], citation_ids: [] }],
  }} />);
  expect(screen.getByText('BIS Bandhu')).toBeInTheDocument();
  expect(screen.queryByText('Grounded answer')).toBeNull();
  expect(screen.queryByText('Evidence insufficient')).toBeNull();
  expect(document.querySelector('.sources')).toBeNull();
});

it('uses the backend response kind for conversation, clarification, limitation, and grounded guidance', () => {
  const cases = [
    ['conversation', 'BIS Bandhu'],
    ['clarification', 'Need more details'],
    ['limitation', 'Evidence insufficient'],
    ['grounded_guidance', 'Grounded answer'],
  ] as const;
  for (const [response_kind, label] of cases) {
    render(<ChatMessage role="assistant" text="Safe response" response={{ ...response, response_kind, grounded: response_kind === 'grounded_guidance', insufficient_evidence: response_kind === 'limitation', needs_clarification: response_kind === 'clarification', generation_mode: response_kind === 'conversation' ? 'conversation' : response_kind === 'clarification' ? 'clarification' : response_kind === 'limitation' ? 'abstention' : 'extractive_fallback' }} />);
    expect(screen.getByText(label)).toBeInTheDocument();
    cleanup();
  }
});

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
  expect(screen.getByRole('heading', { name: 'What this means for you' })).toBeInTheDocument();
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
  for (const heading of ['Applicable standards', 'What this means for you', 'Your compliance checklist', 'Important to know']) expect(screen.getAllByRole('heading', { name: heading }).length).toBeGreaterThan(0);
  expect(screen.getAllByRole('heading', { name: /Verified sources 2/i })).toHaveLength(1);
  expect(screen.getAllByText('IS 15644 is primary.')).toHaveLength(1);
  for (const text of ['IS 9873 may apply.', 'The cited material covers electric toys.', 'This is user-provided context, not BIS evidence.', 'First checklist item.', 'Second checklist item.', 'Open the cited primary standard.', 'Evidence is limited to the cited material.', 'Verify before relying on this guidance.']) expect(screen.getByText(text)).toBeInTheDocument();
  expect(document.querySelector('.journey-checklist')).toHaveTextContent('Open the cited primary standard.');
  expect(screen.getByRole('link', { name: 'Page 4' })).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: /View evidence/i })).toHaveLength(2);
});

it('localizes Tamil and Bengali journey headings without translating evidence content', () => {
  const journeyResponse = { ...response, answer_sections: [
    { type: 'explanation' as const, title: 'Why it applies', content: 'IS 15644 is primary.', items: [], citation_ids: ['S1'] },
    { type: 'important' as const, title: 'Important condition', content: 'IS 9873 may apply where applicable.', items: [], citation_ids: ['S1'] },
  ] };
  for (const [language, headings] of [
    ['ta', ['எளிய சொற்களில்', 'தெரிந்துகொள்ள முக்கியம்']],
    ['bn', ['সহজ ভাষায়', 'জানা গুরুত্বপূর্ণ']],
  ] as const) {
    localStorage.setItem('bis-assistant-language', language);
    render(<LanguageProvider><ChatMessage role="assistant" text={journeyResponse.answer} response={journeyResponse} presentation="compliance-journey" /></LanguageProvider>);
    for (const heading of headings) expect(screen.getAllByRole('heading', { name: heading }).length).toBeGreaterThan(0);
    expect(screen.getByText('IS 15644 is primary.')).toBeInTheDocument();
    expect(screen.getByText('IS 9873 may apply where applicable.')).toBeInTheDocument();
    cleanup();
  }
});

it('uses structural labels and localized source controls for every journey locale', () => {
  const journeyResponse = { ...response, answer_sections: [
    { type: 'direct_answer' as const, title: 'Standards found', content: 'IS 15644 is primary.', items: [], citation_ids: ['S1'] },
    { type: 'explanation' as const, title: 'Reason', content: 'The cited material covers electric toys.', items: [], citation_ids: ['S1'] },
    { type: 'next_steps' as const, title: 'Your next action', content: null, items: ['Review the cited source.'], citation_ids: ['S1'] },
    { type: 'important' as const, title: 'Important condition', content: 'Verify before relying on this guidance.', items: [], citation_ids: ['S1'] },
  ] };
  for (const language of ['en', 'hi', 'mr', 'ta', 'bn'] as const) {
    const labels = translations[language];
    localStorage.setItem('bis-assistant-language', language);
    render(<LanguageProvider><ChatMessage role="assistant" text={journeyResponse.answer} response={journeyResponse} presentation="compliance-journey" /></LanguageProvider>);
    for (const heading of [labels.journeyApplicable, labels.sectionSummary, labels.sectionExplanation, labels.journeyChecklist, labels.sectionNextSteps, labels.sectionImportant]) expect(screen.getAllByRole('heading', { name: heading }).length).toBeGreaterThan(0);
    expect(screen.getByRole('heading', { name: new RegExp(`${labels.verifiedSources} 2`) })).toBeInTheDocument();
    expect(screen.getByText(labels.viewVerifiedDetails)).toBeInTheDocument();
    expect(screen.getByText('IS 15644 is primary.')).toBeInTheDocument();
    expect(screen.getAllByText('a very long trusted source filename.pdf').length).toBeGreaterThan(0);
    if (language !== 'en') {
      for (const english of ['In simple terms', 'Important to know', 'What this means for you', 'What to do next', 'Your compliance checklist', 'Verified sources', 'View verified source details', 'Applicable standards']) expect(screen.queryByText(english, { exact: true })).toBeNull();
    }
    cleanup();
  }
});

it('localizes citation controls and the suggested-replies label in every locale without changing evidence', () => {
  for (const language of ['en', 'hi', 'mr', 'ta', 'bn'] as const) {
    localStorage.setItem('bis-assistant-language', language);
    const labels = translations[language];
    render(<LanguageProvider><ChatMessage role="assistant" text={response.answer} response={response} suggestedActions={[{ kind: 'chat_question', label: labels.suggestedRoadmap, question: 'Show my complete compliance roadmap' }]} onSuggestedAction={() => undefined} /></LanguageProvider>);
    expect(screen.getByRole('group', { name: labels.suggestedReplies })).toBeInTheDocument();
    expect(screen.getByText(`${labels.source} S1`)).toBeInTheDocument();
    expect(screen.getByText(`${labels.page} 4`)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: new RegExp(labels.viewEvidence) })).not.toHaveLength(0);
    expect(screen.getAllByRole('link').some((link) => link.textContent?.includes(labels.openSourcePdf))).toBe(true);
    expect(screen.getByText('a very long trusted source filename.pdf')).toBeInTheDocument();
    cleanup();
  }
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

it('shows a safe official handoff for an evidence limitation without inventing a citation', () => {
  render(<ChatMessage role="assistant" text="BIS Bandhu cannot authenticate this HUID." response={{
    ...response, answer: 'BIS Bandhu cannot authenticate this HUID.', grounded: false,
    insufficient_evidence: true, evidence_count: 0, citations: [], response_kind: 'limitation',
    official_next_step_url: 'https://www.bis.gov.in/bis-apps/?lang=en',
  }} />);
  expect(screen.getByText('Evidence insufficient')).toBeInTheDocument();
  expect(screen.queryByText(/Source S/)).toBeNull();
  expect(screen.getByRole('link', { name: 'Continue on the official BIS website ↗' })).toHaveAttribute('href', 'https://www.bis.gov.in/bis-apps/?lang=en');
  cleanup();
  render(<ChatMessage role="assistant" text="No evidence" response={{
    ...response, grounded: false, insufficient_evidence: true, evidence_count: 0,
    citations: [], response_kind: 'limitation', official_next_step_url: 'https://example.com/phishing',
  }} />);
  expect(screen.queryByRole('link')).toBeNull();
});
