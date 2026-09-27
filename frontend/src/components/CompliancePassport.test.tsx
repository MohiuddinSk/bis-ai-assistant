import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { CompliancePassport, compliancePassportId, passportCitations, passportStatus } from './CompliancePassport';
import { CompliancePrintReport } from './CompliancePrintReport';
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

function renderPassport(language: 'en' | 'hi' | 'mr' | 'ta' | 'bn' = 'en', response = guidance) {
  localStorage.setItem('bis-assistant-language', language);
  return render(<LanguageProvider><CompliancePassport profile={profile} guidance={response} generatedAt={generatedAt} /></LanguageProvider>);
}

function renderPrintReport(language: 'en' | 'hi' | 'mr' | 'ta' | 'bn' = 'en', response = guidance) {
  localStorage.setItem('bis-assistant-language', language);
  return render(<LanguageProvider><CompliancePrintReport profile={profile} guidance={response} generatedAt={generatedAt} /></LanguageProvider>);
}

it('renders cited findings, verification limits, and at most three actions without promoting user context', () => {
  renderPassport();
  const passport = within(screen.getByRole('region', { name: 'Compliance Passport' }));
  expect(passport.getByText(compliancePassportId(profile, guidance))).toBeInTheDocument();
  expect(passport.getByText('User-provided information — not verified BIS evidence.')).toBeInTheDocument();
  expect(passport.queryByText('IS 15644 applies where applicable.')).not.toBeInTheDocument();
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
  expect(screen.queryByText('IS 15644 applies where applicable.')).not.toBeInTheDocument();
  expect(screen.getByText('manual.pdf')).toBeInTheDocument();
  cleanup();
  renderPassport('mr');
  expect(screen.getByRole('region', { name: 'अनुपालन पासपोर्ट' })).toBeInTheDocument();
  expect(screen.getByText('उद्धृत पुरावा')).toBeInTheDocument();
  expect(screen.queryByText('IS 15644 applies where applicable.')).not.toBeInTheDocument();
  expect(screen.getByText('manual.pdf')).toBeInTheDocument();
});

it('uses Tamil and Bengali profile labels in the passport and printable report content', () => {
  for (const [language, labels] of [['ta', ['தயாரிப்பு', 'மின்சார வகை', 'நோக்கமுள்ள வயது குழு', 'தற்போதைய நிலை', 'வழிகாட்டல் இலக்கு']], ['bn', ['পণ্য', 'বিদ্যুতের ধরন', 'নির্ধারিত বয়সের দল', 'বর্তমান ধাপ', 'নির্দেশনার লক্ষ্য']]] as const) {
    cleanup(); renderPassport(language);
    for (const label of labels) expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    expect(screen.getByText('Battery toy')).toBeInTheDocument(); expect(screen.getByText('manual.pdf')).toBeInTheDocument();
    cleanup(); renderPrintReport(language);
    const reportElement = document.querySelector<HTMLElement>('article.compliance-print-report');
    expect(reportElement).not.toBeNull();
    const report = within(reportElement!);
    for (const label of labels) expect(report.getAllByText(label).length).toBeGreaterThan(0);
    expect(report.getByText('Battery toy')).toBeInTheDocument(); expect(report.getByText('manual.pdf')).toBeInTheDocument();
  }
});

it('renders reviewed localized Wizard content unchanged in the Passport and print report', () => {
  for (const [language, standard, action] of [
    ['hi', 'IS 15644 प्राथमिक मानक है। उद्धृत IS 9873 भाग, जहाँ लागू हों, द्वितीयक आवश्यकताएँ हैं।', 'उद्धृत प्राथमिक मानक और जहाँ लागू हों, द्वितीयक भागों को पहले देखें।'],
    ['mr', 'IS 15644 हे प्राथमिक मानक आहे. उद्धृत IS 9873 भाग, जेथे लागू असतील तेथे, दुय्यम आवश्यकता आहेत.', 'उद्धृत प्राथमिक मानक आणि जेथे लागू असतील ते दुय्यम भाग प्रथम तपासा.'],
    ['ta', 'IS 15644 முதன்மை தரநிலையாகும். மேற்கோள் காட்டப்பட்ட IS 9873 பகுதிகள், பொருந்தும் இடங்களில், இரண்டாம் நிலை தேவைகள்.', 'மேற்கோள் காட்டப்பட்ட முதன்மை தரநிலையையும், பொருந்தும் இடங்களில் இரண்டாம் நிலை பகுதிகளையும் முதலில் பாருங்கள்.'],
    ['bn', 'IS 15644 প্রাথমিক মান। উদ্ধৃত IS 9873 অংশগুলি, যেখানে প্রযোজ্য, গৌণ প্রয়োজনীয়তা।', 'উদ্ধৃত প্রাথমিক মান এবং যেখানে প্রযোজ্য গৌণ অংশগুলি আগে দেখুন।'],
  ] as const) {
    const localized = {
      ...guidance,
      answer: `${standard}\n\n${action}`,
      answer_sections: guidance.answer_sections!.map((section, index) => index === 0
        ? { ...section, content: standard }
        : index === 3 ? { ...section, items: [action] } : section),
    };
    cleanup(); renderPassport(language, localized);
    expect(screen.getByText(standard)).toBeInTheDocument();
    expect(screen.getByText(action)).toBeInTheDocument();
    expect(screen.getByText('manual.pdf')).toBeInTheDocument();
    cleanup(); renderPrintReport(language, localized);
    const report = document.querySelector<HTMLElement>('article.compliance-print-report');
    expect(report).not.toBeNull();
    expect(within(report!).getByText(standard)).toBeInTheDocument();
    expect(within(report!).getByText(action)).toBeInTheDocument();
    expect(within(report!).getByText('manual.pdf')).toBeInTheDocument();
  }
});

it('keeps the responsive header, metadata, profile rows, and localized section cues aligned in every language', () => {
  for (const [language, simpleTerms, important] of [
    ['en', 'In simple terms', 'Important to know'],
    ['hi', 'सरल शब्दों में', 'जानने योग्य महत्वपूर्ण बातें'],
    ['mr', 'सोप्या शब्दांत', 'जाणून घेण्यासारखे महत्त्वाचे मुद्दे'],
    ['ta', 'எளிய சொற்களில்', 'தெரிந்துகொள்ள முக்கியம்'],
    ['bn', 'সহজ ভাষায়', 'জানা গুরুত্বপূর্ণ'],
  ] as const) {
    cleanup();
    renderPassport(language);
    const passport = document.querySelector<HTMLElement>('.compliance-passport');
    expect(passport).not.toBeNull();
    const header = passport!.querySelector<HTMLElement>('.passport-heading');
    expect(header).not.toBeNull();
    expect(header!.querySelector('.passport-identity')).not.toBeNull();
    expect(header!.querySelector('.passport-status')).not.toBeNull();
    expect(header!.querySelector('.passport-metadata')).not.toBeNull();
    expect(header!.querySelector('.passport-notice')).not.toBeNull();
    expect(header!.querySelector('.passport-report-id')).toHaveTextContent(compliancePassportId(profile, guidance));
    expect(passport!.querySelectorAll('.passport-profile dl > dt')).toHaveLength(5);
    expect(screen.getAllByText(simpleTerms).length).toBe(1);
    expect(screen.getAllByText(important).length).toBe(1);
    if (language !== 'en') {
      expect(within(passport!).queryByText('In simple terms', { exact: true })).toBeNull();
      expect(within(passport!).queryByText('Important to know', { exact: true })).toBeNull();
      expect(within(passport!).queryByText('What this means for you', { exact: true })).toBeNull();
    }

    cleanup();
    renderPrintReport(language);
    const report = document.querySelector<HTMLElement>('article.compliance-print-report');
    expect(report).not.toBeNull();
    expect(report!.querySelector('.passport-heading .passport-metadata')).not.toBeNull();
    expect(report!.querySelectorAll('.passport-profile dl > dt')).toHaveLength(5);
    expect(within(report!).getAllByText(simpleTerms).length).toBe(1);
    expect(within(report!).getAllByText(important).length).toBe(1);
    if (language !== 'en') expect(within(report!).queryByText('In simple terms', { exact: true })).toBeNull();
  }
});

it('prints a validated supporting quote instead of a noisy excerpt while preserving citation identity', () => {
  const noisy = 'Noisy OCR excerpt | Column 1 | Column 2 | repeated source material.';
  const quote = 'IS 15644 applies where applicable.';
  const response = { ...guidance, citations: [{ ...guidance.citations[0], excerpt: noisy, supporting_quote: quote }] };
  renderPrintReport('en', response);
  const source = document.querySelector<HTMLElement>('.passport-source')!;
  expect(source).toHaveTextContent('S1');
  expect(source).toHaveTextContent('manual.pdf');
  expect(source).toHaveTextContent('Pages 4');
  expect(source).toHaveTextContent(quote);
  expect(source).not.toHaveTextContent(noisy);
  const paragraphs = source.querySelectorAll('p');
  expect(paragraphs).toHaveLength(2);
  expect(paragraphs[0].parentElement).toBe(source);
  expect(paragraphs[1].parentElement).toBe(source);
  expect(paragraphs[1]).toHaveTextContent(quote);
});

it('prints metadata only when no supporting quote is available and preserves source order', () => {
  const first = { ...guidance.citations[0], excerpt: 'Raw evidence one.' };
  const second = { ...guidance.citations[1], citation_id: 'S3', source_filename: 'second.pdf', page_start: 7, page_end: 7, chunk_id: 'chunk-3', excerpt: 'Raw evidence two.' };
  const response = { ...guidance, citations: [first, second], answer_sections: guidance.answer_sections!.map((section) => ({ ...section, citation_ids: section.citation_ids.includes('S1') ? ['S1', 'S3'] : section.citation_ids })) };
  renderPrintReport('en', response);
  const blocks = Array.from(document.querySelectorAll<HTMLElement>('.passport-source'));
  expect(blocks).toHaveLength(2);
  expect(blocks[0]).toHaveTextContent('S1');
  expect(blocks[0]).toHaveTextContent('manual.pdf');
  expect(blocks[0]).toHaveTextContent('Pages 4');
  expect(blocks[1]).toHaveTextContent('S3');
  expect(blocks[1]).toHaveTextContent('second.pdf');
  expect(blocks[1]).toHaveTextContent('Pages 7');
  expect(blocks[0]).not.toHaveTextContent('Raw evidence one.');
  expect(blocks[1]).not.toHaveTextContent('Raw evidence two.');
  for (const block of blocks) {
    expect(block.querySelectorAll('p')).toHaveLength(1);
    expect(block.querySelector('p')?.parentElement).toBe(block);
  }
});

it('keeps all printable citation metadata and evidence in the protected citation wrapper', () => {
  const quote = 'Validated verbatim supporting quote.';
  const response = { ...guidance, citations: [{ ...guidance.citations[0], supporting_quote: quote }] };
  renderPrintReport('en', response);
  const source = document.querySelector<HTMLElement>('.compliance-print-report .passport-source')!;
  expect(source).toBeInstanceOf(HTMLElement);
  expect(source.tagName).toBe('ARTICLE');
  expect(source).toHaveTextContent('S1');
  expect(source).toHaveTextContent('manual.pdf');
  expect(source).toHaveTextContent('Pages 4');
  expect(source).toHaveTextContent(quote);
  expect(source.parentElement?.querySelectorAll('.passport-source')).toHaveLength(1);
});
