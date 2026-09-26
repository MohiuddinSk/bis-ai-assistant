import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { CompliancePassport, compliancePassportId, passportCitations, passportStatus } from './CompliancePassport';
import { LanguageProvider } from '../i18n/LanguageContext';
import type { ChatResponse } from '../types/chat';
import type { ComplianceProfile } from '../types/compliance';

const profile: ComplianceProfile = { role: 'manufacturer', product_description: 'Battery toy', power_type: 'battery_operated', intended_age_group: '3_to_8', goal: 'identify_standards', application_stage: 'researching', additional_context: null };
const guidance: ChatResponse = { answer: 'Grounded guidance.', grounded: true, insufficient_evidence: false, evidence_count: 1, citations: [{ citation_id: 'S1', source_filename: 'manual.pdf', page_start: 4, page_end: 4, chunk_id: 'chunk-1', excerpt: 'IS 15644 applies where applicable.' }, { citation_id: 'S2', source_filename: 'unlinked.pdf', page_start: 9, page_end: 9, chunk_id: 'chunk-2', excerpt: 'This evidence is not used.' }], model: 'test', generation_mode: 'extractive_fallback', disclaimer: 'Verify before relying on this guidance.', answer_sections: [
  { type: 'direct_answer', title: 'Standards', content: 'IS 15644 applies.', items: [], citation_ids: ['S1'] },
  { type: 'explanation', title: 'Findings', content: 'Evidence-backed finding.', items: [], citation_ids: ['S1'] },
  { type: 'explanation', title: 'User context', content: 'Battery toy context from the user.', items: [], citation_ids: [] },
  { type: 'next_steps', title: 'Actions', content: null, items: ['First action', 'Second action', 'Third action', 'Fourth action'], citation_ids: ['S1'] },
  { type: 'important', title: 'Limitations', content: 'Exact fees, timeline, labs, forms and remaining steps are not established.', items: [], citation_ids: ['S1'] },
] };
const generatedAt = new Date('2026-01-02T03:04:05.000Z');

afterEach(() => { cleanup(); localStorage.clear(); });

function renderPassport(language: 'en' | 'hi' | 'mr' = 'en') {
  localStorage.setItem('bis-assistant-language', language);
  return render(<LanguageProvider><CompliancePassport profile={profile} guidance={guidance} generatedAt={generatedAt} /></LanguageProvider>);
}

it('renders cited findings, verification limits, and at most three actions without promoting user context', () => {
  renderPassport();
  const passport = within(screen.getByRole('region', { name: 'Compliance Passport' }));
  expect(passport.getByText(compliancePassportId(profile, guidance))).toBeInTheDocument();
  expect(passport.getByText('User-provided information — not verified BIS evidence.')).toBeInTheDocument();
  expect(passport.getByText('IS 15644 applies where applicable.')).toBeInTheDocument();
  expect(passport.getByText('manual.pdf')).toBeInTheDocument();
  expect(passport.queryByText('unlinked.pdf')).not.toBeInTheDocument();
  expect(passport.queryByText('Battery toy context from the user.')).not.toBeInTheDocument();
  expect(passport.getByRole('heading', { name: 'Verification needed' }).parentElement).toHaveTextContent('Exact fees, timeline, labs, forms and remaining steps are not established.');
  expect(passport.getByRole('heading', { name: 'Missing profile information' }).parentElement).not.toHaveTextContent('Exact fees');
  expect(passport.queryByText('chunk-1')).not.toBeInTheDocument();
  const actions = passport.getByRole('heading', { name: 'Next three actions' }).parentElement!;
  expect(within(actions).getAllByRole('listitem')).toHaveLength(3);
});

it('derives language-independent identity from canonical profile and cited evidence only', () => {
  const hindiVariant = { ...guidance, answer: 'हिंदी मार्गदर्शन', answer_sections: guidance.answer_sections?.map((section) => ({ ...section, title: `हिंदी ${section.title}`, content: section.content === 'Evidence-backed finding.' ? 'हिंदी निष्कर्ष' : section.content })) };
  const marathiVariant = { ...guidance, answer: 'मराठी मार्गदर्शन', answer_sections: guidance.answer_sections?.map((section) => ({ ...section, title: `मराठी ${section.title}`, content: section.content === 'Evidence-backed finding.' ? 'मराठी निष्कर्ष' : section.content })) };
  expect(compliancePassportId(profile, guidance)).toBe(compliancePassportId(profile, hindiVariant));
  expect(compliancePassportId(profile, guidance)).toBe(compliancePassportId(profile, marathiVariant));
  expect(compliancePassportId({ ...profile, product_description: 'Edited battery toy' }, guidance)).not.toBe(compliancePassportId(profile, guidance));
  expect(passportCitations(guidance).map((citation) => citation.citation_id)).toEqual(['S1']);
});

it('keeps the report ID and generated timestamp across English, Hindi, and Marathi variants', () => {
  const readMetadata = () => ({ id: screen.getByText(/BIS-CP-/).textContent, time: screen.getByRole('time').getAttribute('datetime') });
  renderPassport('en'); const english = readMetadata(); cleanup();
  renderPassport('hi'); const hindi = readMetadata(); cleanup();
  renderPassport('mr'); const marathi = readMetadata();
  expect(hindi).toEqual(english);
  expect(marathi).toEqual(english);
});

it('derives missing-information and verification states only from profile and grounded evidence', () => {
  expect(passportStatus({ ...profile, power_type: 'not_sure' }, guidance)).toBe('needs_information');
  expect(passportStatus(profile, { ...guidance, grounded: false })).toBe('needs_verification');
  expect(passportStatus(profile, { ...guidance, answer_sections: [{ ...guidance.answer_sections![0], citation_ids: [] }] })).toBe('needs_verification');
});

it('localizes passport UI labels without changing sources or standard identifiers', () => {
  renderPassport('hi');
  expect(screen.getByRole('region', { name: 'अनुपालन पासपोर्ट' })).toBeInTheDocument();
  expect(screen.getByText('उद्धृत साक्ष्य')).toBeInTheDocument();
  expect(screen.getByText('IS 15644 applies where applicable.')).toBeInTheDocument();
  expect(screen.getByText('manual.pdf')).toBeInTheDocument();
  cleanup();
  renderPassport('mr');
  expect(screen.getByRole('region', { name: 'अनुपालन पासपोर्ट' })).toBeInTheDocument();
  expect(screen.getByText('उद्धृत पुरावा')).toBeInTheDocument();
  expect(screen.getByText('IS 15644 applies where applicable.')).toBeInTheDocument();
  expect(screen.getByText('manual.pdf')).toBeInTheDocument();
});
