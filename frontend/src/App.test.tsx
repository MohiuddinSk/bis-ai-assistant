import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from './App';

const answer = { answer: 'IS 15644 is the primary standard.', grounded: true, insufficient_evidence: false, evidence_count: 1, citations: [{ citation_id: 'S1', source_filename: 'manual.pdf', page_start: 4, page_end: 4, chunk_id: 'internal', excerpt: 'IS 15644 applies.' }], model: 'test', generation_mode: 'llm' as const, disclaimer: 'Verify.' };
const response = (body: unknown) => ({ ok: true, json: async () => body });

beforeEach(() => { window.history.replaceState(null, '', '/'); localStorage.clear(); vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(response(url.includes('health') ? { status: 'ready' } : answer)))); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); delete (window as Window & { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition; delete (window as Window & { SpeechRecognition?: unknown }).SpeechRecognition; });

async function openAssistant() {
  await screen.findByRole('status');
  await userEvent.setup().click(screen.getByRole('button', { name: 'Assistant' }));
}

it('opens a stable standards URL directly and keeps catalogue errors honest when the endpoint is unavailable', async () => {
  window.location.hash = '#/standards';
  render(<App />);
  expect(await screen.findByRole('heading', { name: 'Search verified standard metadata' })).toBeInTheDocument();
  expect(await screen.findByText('The verified catalogue could not be loaded. Please try again or use the official BIS search.')).toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole('contentinfo').querySelector('button:last-child') as HTMLButtonElement);
  expect(window.location.hash).toBe('#/services');
  expect(screen.getByRole('heading', { name: 'BIS Bandhu services' })).toBeInTheDocument();
});

it('opens Standards directly without creating a chat request', async () => {
  render(<App />); await screen.findByRole('status');
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Standards' }));
  expect(window.location.hash).toBe('#/standards');
  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(0);
});

it('opens Testing Labs and Hallmarking as distinct, refreshable routes without chat requests', async () => {
  window.location.hash = '#/testing-labs';
  render(<App />);
  await screen.findByRole('heading', { name: 'Testing laboratories' });
  const nav = screen.getByRole('navigation');
  expect(within(nav).getByRole('button', { name: 'Testing Labs' })).toHaveAttribute('aria-current', 'page');
  expect(within(nav).queryAllByRole('button', { current: 'page' })).toHaveLength(1);
  await userEvent.setup().click(within(nav).getByRole('button', { name: 'Hallmarking' }));
  expect(window.location.hash).toBe('#/consumers/hallmarking');
  expect(screen.getByRole('heading', { name: 'Hallmarking guidance' })).toBeInTheDocument();
  expect(within(nav).getByRole('button', { name: 'Hallmarking' })).toHaveAttribute('aria-current', 'page');
  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(0);
});

it('hands an edited hallmarking question to the shared Assistant with the selected audience', async () => {
  window.location.hash = '#/consumers/hallmarking';
  render(<App />);
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'How can a jeweller get started with BIS hallmarking?' }));
  const question = screen.getByRole('textbox', { name: 'Your hallmarking question' });
  expect(question).toHaveValue('How can a jeweller get started with BIS hallmarking?');
  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(0);
  await user.type(question, ' Please include registration.');
  await user.click(screen.getByRole('button', { name: 'Ask Bandhu' }));
  await screen.findByText('IS 15644 is the primary standard.');
  expect(window.location.hash).toBe('#/assistant');
  const chatCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(([url]) => String(url).includes('/api/chat'));
  expect(chatCall).toBeDefined();
  expect(JSON.parse(chatCall![1].body)).toMatchObject({
    question: 'How can a jeweller get started with BIS hallmarking? Please include registration.',
    audience: 'manufacturer',
  });
});

it('updates hallmarking guidance in all five languages without losing the draft or route', async () => {
  window.location.hash = '#/consumers/hallmarking';
  render(<App />);
  const user = userEvent.setup();
  const question = document.getElementById('hallmark-question') as HTMLTextAreaElement;
  await user.type(question, 'HUID ABC123');
  const headings = [
    ['hi', 'हॉलमार्किंग मार्गदर्शन', 'BIS Care में HUID जाँचें ↗'],
    ['mr', 'हॉलमार्किंग मार्गदर्शन', 'BIS Care मध्ये HUID तपासा ↗'],
    ['ta', 'ஹால்மார்க்கிங் வழிகாட்டல்', 'BIS Care-இல் HUID சரிபார்க்கவும் ↗'],
    ['bn', 'হলমার্কিং নির্দেশনা', 'BIS Care-এ HUID যাচাই করুন ↗'],
    ['en', 'Hallmarking guidance', 'Verify HUID in BIS Care ↗'],
  ] as const;
  for (const [language, heading, service] of headings) {
    await user.selectOptions(document.getElementById('language') as HTMLSelectElement, language);
    expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: service })).toBeInTheDocument();
    expect(question).toHaveValue('HUID ABC123');
    expect(window.location.hash).toBe('#/consumers/hallmarking');
  }
  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(0);
});

it('keeps concise navigation keyboard-operable and reaches guidance and hallmarking without a chat request', async () => {
  render(<App />); await screen.findByRole('status');
  const user = userEvent.setup();
  expect(within(screen.getByRole('navigation')).queryByRole('button', { name: 'Industry' })).toBeNull();
  const hallmarking = within(screen.getByRole('navigation')).getByRole('button', { name: 'Hallmarking' });
  hallmarking.focus();
  await user.keyboard('{Enter}');
  expect(window.location.hash).toBe('#/consumers/hallmarking');
  expect(hallmarking).toHaveAttribute('aria-current', 'page');
  expect(screen.getByText(/does not verify HUID authenticity/i)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Verify HUID in BIS Care ↗' })).toHaveAttribute('href', 'https://www.bis.gov.in/bis-apps/?lang=en');
  await user.click(screen.getByRole('contentinfo').querySelector('button:last-child') as HTMLButtonElement);
  await user.click(screen.getByRole('button', { name: 'Certification guidance →' }));
  expect(window.location.hash).toBe('#/industry/certification-guide');
  expect(screen.getByText('Track the official process')).toBeInTheDocument();
  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(0);
});

it('features verified helmet metadata only in the unfiltered view and keeps searched API order', async () => {
  const helmet={identifier:'IS 4151:2015',title:'Protective Helmet for Two Wheeler Riders',category:'Helmet',edition_year:'2015',status:'Verified from product manual',official_url:'https://www.bis.gov.in/helmet.pdf',retrieved_at:'2024-12',provenance:'BIS product manual',evidence_filename:'helmet.pdf',evidence_page:1};
  const second={...helmet,identifier:'IS 9999:2020',title:'Other verified test record'};
  vi.stubGlobal('fetch',vi.fn((url:string)=>Promise.resolve(response(url.includes('health')?{status:'ready'}:url.includes('/api/catalogue/')?{query:'',record_count:2,last_updated:'2024-12',results:[second,helmet]}:answer))));
  window.location.hash='#/standards'; render(<App />);
  expect(await screen.findByText(helmet.title)).toBeInTheDocument();
  const cards=Array.from(document.querySelectorAll('.reference-card'));
  expect(cards[0]).toHaveTextContent(helmet.identifier);
  expect(cards[0]).toHaveClass('featured-standard');
  const user=userEvent.setup();
  await user.type(screen.getByLabelText('IS number, product, or keyword'),'other');
  await user.click(screen.getByRole('button',{name:'Search'}));
  await waitFor(()=>expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url])=>String(url).includes('/api/catalogue/'))).toHaveLength(2));
  expect(document.querySelector('.reference-card')).toHaveTextContent(second.identifier);
  expect(document.querySelector('.featured-standard')).toBeNull();
});

it('loads a non-featured verified detail from its direct URL without inventing technical guidance', async () => {
  const electric={identifier:'IS 15644:2006',title:'Safety of Electric Toys',category:'Toys',edition_year:'2006',status:'Identifier and title listed by BIS; this metadata is not an applicability decision',official_url:'https://www.bis.gov.in/product-certification/products-under-compulsory-certification/scheme-1/?lang=en',retrieved_at:'2026-09-29',provenance:'BIS Scheme-I page',evidence_filename:null,evidence_page:null};
  vi.stubGlobal('fetch',vi.fn((url:string)=>Promise.resolve(response(url.includes('health')?{status:'ready'}:url.includes('/api/catalogue/')?electric:answer))));
  window.location.hash='#/standards/detail?is=IS%2015644%3A2006';
  render(<App />);
  expect(await screen.findByText('Safety of Electric Toys')).toBeInTheDocument();
  expect(screen.getByText(/does not replace the official standard or make an applicability decision/)).toBeInTheDocument();
  expect(screen.getByRole('link',{name:'Open official source ↗'})).toHaveAttribute('href',electric.official_url);
  expect(window.location.hash).toBe('#/standards/detail?is=IS%2015644%3A2006');
  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url])=>String(url).includes('/api/chat'))).toHaveLength(0);
});

it('renders only provenance-bearing catalogue records returned by the API', async () => {
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(response(url.includes('health') ? { status: 'ready' } : url.includes('/api/catalogue/') ? {
    query: 'IS 4151', record_count: 1, last_updated: '2024-12', coverage_note: 'Only locally verified metadata is listed.', results: [{ identifier: 'IS 4151:2015', title: 'Protective Helmet for Two Wheeler Riders', category: 'Helmet', edition_year: '2015', status: 'Verified', official_url: 'https://www.bis.gov.in/example', retrieved_at: '2024-12', provenance: 'BIS Product Manual, page 1', evidence_filename: 'PM_IS_4151_-Dec-24.pdf', evidence_page: 1 }],
  } : answer))));
  window.location.hash = '#/standards';
  render(<App />);
  expect(await screen.findByText('Protective Helmet for Two Wheeler Riders')).toBeInTheDocument();
  expect(screen.getByText('1 verified catalogue record · Latest verified metadata: 2024-12')).toBeInTheDocument();
  expect(screen.queryByText(/Illustrative cooking appliance|Demo data/i)).toBeNull();
});

it('keeps consumer guidance as an official handoff rather than simulated verification', async () => {
  window.location.hash = '#/consumers';
  render(<App />); await screen.findByRole('status');
  expect(screen.getAllByText(/does not verify a licence, product, HUID/i)).not.toHaveLength(0);
  expect(screen.getByRole('link', { name: 'Open official BIS consumer information ↗' })).toHaveAttribute('href', 'https://www.bis.gov.in/consumer-overview/');
  expect(screen.getByRole('link', { name: 'Open official BIS complaints information ↗' })).toHaveAttribute('href', 'https://www.bis.gov.in/consumer-overview/online-complaint-registration/?lang=en');
});

it('localizes detailed reference-page controls in every supported language without leaving its deep route', async () => {
  const labels = { en: 'IS number, product, or keyword', hi: 'IS नंबर, उत्पाद या कीवर्ड', mr: 'IS क्रमांक, उत्पादन किंवा कीवर्ड', ta: 'IS எண், தயாரிப்பு அல்லது முக்கியச்சொல்', bn: 'IS নম্বর, পণ্য বা কীওয়ার্ড' } as const;
  for (const [language, label] of Object.entries(labels)) {
    cleanup();
    window.history.replaceState(null, '', '/');
    window.location.hash = '#/standards';
    render(<App />); await screen.findByRole('status');
    await userEvent.setup().selectOptions(document.getElementById('language') as HTMLSelectElement, language);
    expect(screen.getByLabelText(label)).toBeInTheDocument();
    expect(window.location.hash).toBe('#/standards');
  }
});

it('opens on the BIS Bandhu homepage with working journeys', async () => {
  render(<App />); await screen.findByRole('status');
  expect(screen.getByRole('heading', { name: /Indian Standards, made clearer/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Find a Standard' })).toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole('button', { name: /Create a Compliance Passport/ }));
  expect(screen.getByText('BIS Bandhu · Compliance Passport')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Compliance Wizard' })).toBeInTheDocument();
});

it('prefills the supported example for review and sends it only after Ask Bandhu', async () => {
  render(<App />); await screen.findByRole('status');
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Battery-operated toy standard' }));
  expect(screen.getByLabelText('Ask about a product, standard or BIS process')).toHaveValue('Which standard applies to a battery-operated toy?');
  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(0);
  await user.click(within(document.querySelector('.hero-search') as HTMLElement).getByRole('button', { name: 'Ask Bandhu' }));
  expect(await screen.findByText(answer.answer)).toBeInTheDocument();
  const chatCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(([url]) => String(url).includes('/api/chat'));
  expect(JSON.parse(String((chatCall?.[1] as RequestInit).body)).question).toBe('Which standard applies to a battery-operated toy?');
  expect(screen.getByText('manual.pdf')).toBeInTheDocument();
});

it('keeps a selected language and exposes the assistant view', async () => {
  render(<App />); await screen.findByRole('status'); const user = userEvent.setup();
  await user.selectOptions(screen.getByLabelText('Language'), 'hi');
  await user.click(screen.getByRole('button', { name: 'सहायक' }));
  expect(screen.getByLabelText('भाषा')).toHaveValue('hi');
  expect(screen.getByRole('heading', { name: 'विश्वास से पूछें। साक्ष्य जाँचें।' })).toBeInTheDocument();
  expect(screen.getByLabelText('उत्पाद, मानक या BIS प्रक्रिया के बारे में पूछें')).toBeInTheDocument();
});

it('preserves in-progress Wizard answers while visiting the Assistant', async () => {
  render(<App />);
  await screen.findByRole('status');
  const user = userEvent.setup();

  await user.click(screen.getByRole('button', { name: 'Compliance Wizard' }));
  await user.click(screen.getByRole('button', { name: 'Manufacturer' }));
  await user.type(screen.getByLabelText('Product description or type'), 'Battery-operated toy car');
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  await user.click(screen.getByLabelText('Battery-operated'));

  await user.click(screen.getByRole('button', { name: 'Assistant' }));
  await user.click(screen.getByRole('button', { name: 'Compliance Wizard' }));

  expect(screen.getByText('Step 2 of 5')).toBeInTheDocument();
  expect(screen.getByLabelText('Battery-operated')).toBeChecked();
  await user.click(screen.getByRole('button', { name: 'Back' }));
  expect(screen.getByLabelText('Product description or type')).toHaveValue('Battery-operated toy car');
});

it('opens Find a Standard without submitting a chat request', async () => {
  render(<App />);
  await screen.findByRole('status');
  await userEvent.setup().click(screen.getByRole('button', { name: 'Find a Standard' }));

  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(0);
  expect(screen.getByLabelText('I am a:')).toHaveValue('manufacturer');
  expect(screen.getByLabelText('Ask about a product, standard or BIS process')).toHaveFocus();
});

it('opens the Industry card as an editable Manufacturer journey without a chat request', async () => {
  render(<App />);
  await screen.findByRole('status');
  await userEvent.setup().click(screen.getByRole('button', { name: /For industry/ }));

  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(0);
  expect(screen.getByLabelText('I am a:')).toHaveValue('manufacturer');
  expect(screen.getByLabelText('Ask about a product, standard or BIS process')).toHaveFocus();
});

it('opens the Consumer card as an editable Consumer journey without a chat request', async () => {
  render(<App />);
  await screen.findByRole('status');
  await userEvent.setup().click(screen.getByRole('button', { name: /For consumers/ }));

  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(0);
  expect(screen.getByLabelText('I am a:')).toHaveValue('consumer');
  expect(screen.getByLabelText('Ask about a product, standard or BIS process')).toHaveFocus();
});

it('submits the customer product wording as a Manufacturer and renders API evidence', async () => {
  const apiAnswer = { ...answer, answer: 'Mocked product guidance from the backend.', citations: [{ ...answer.citations[0], source_filename: 'mocked-guidance.pdf', excerpt: 'Mocked source excerpt.' }] };
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(response(url.includes('health') ? { status: 'ready' } : apiAnswer))));
  render(<App />);
  await screen.findByRole('status');
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Find a Standard' }));
  await user.type(screen.getByLabelText('Ask about a product, standard or BIS process'), 'What standard applies to my wooden puzzle?{Enter}');

  expect(await screen.findByText('Mocked product guidance from the backend.')).toBeInTheDocument();
  expect(screen.getByText('mocked-guidance.pdf')).toBeInTheDocument();
  expect(screen.queryByText('Mocked source excerpt.')).not.toBeInTheDocument();
  const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(([url]) => String(url).includes('/api/chat'));
  const payload = JSON.parse(String((call?.[1] as RequestInit).body));
  expect(payload.question).toBe('What standard applies to my wooden puzzle?');
  expect(payload.audience).toBe('manufacturer');
  expect(payload.question).not.toContain('battery-operated');
});

it('keeps both recorded questions editable and behind an explicit submit', async () => {
  render(<App />);
  await screen.findByRole('status');
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'New toy series documents' }));
  expect(screen.getByLabelText('Ask about a product, standard or BIS process')).toHaveValue('What documents are required for a new toy series?');
  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(0);
  await user.click(within(document.querySelector('.hero-search') as HTMLElement).getByRole('button', { name: 'Ask Bandhu' }));
  const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(([url]) => String(url).includes('/api/chat'));
  expect(JSON.parse(String((call?.[1] as RequestInit).body))).toMatchObject({question:'What documents are required for a new toy series?',audience:'manufacturer'});
});

it('uses all five language labels while preserving the canonical English suggestion payload', async () => {
  const labels = {
    en: 'Which standard applies to a battery-operated toy?',
    hi: 'बैटरी से चलने वाले खिलौने पर कौन सा मानक लागू होता है?',
    mr: 'बॅटरीवर चालणाऱ्या खेळण्याला कोणते मानक लागू होते?',
    ta: 'மின்கலத்தில் இயங்கும் பொம்மைக்கு எந்த தரநிலை பொருந்தும்?',
    bn: 'ব্যাটারিচালিত খেলনার জন্য কোন মান প্রযোজ্য?',
  } as const;
  for (const [language, label] of Object.entries(labels)) {
    cleanup(); localStorage.clear(); render(<App />); await openAssistant();
    await userEvent.setup().selectOptions(document.getElementById('language') as HTMLSelectElement, language);
    await userEvent.setup().click(screen.getByRole('button', { name: label }));
    expect(await screen.findByText(answer.answer)).toBeInTheDocument();
    const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'));
    const payload = JSON.parse(String((calls.at(-1)?.[1] as RequestInit).body));
    expect(payload.question).toBe('Which standard applies to a battery-operated toy?');
    expect(payload.response_language).toBe(language);
  }
});

it('presents grounded, clarification, and insufficient-evidence responses from the API', async () => {
  for (const [payload, label] of [[answer, 'Grounded answer'], [{ ...answer, grounded: false, needs_clarification: true, generation_mode: 'clarification', citations: [] }, 'Need more details'], [{ ...answer, grounded: false, insufficient_evidence: true, generation_mode: 'abstention' }, 'Evidence insufficient']] as const) {
    cleanup(); vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(response(url.includes('health') ? { status: 'ready' } : payload)))); render(<App />); await openAssistant();
    await userEvent.setup().click(screen.getByRole('button', { name: /battery-operated/i }));
    expect(await screen.findByText(label, { selector: '.answer-status' })).toBeInTheDocument();
  }
});

it('shows citation page and excerpt without exposing the internal chunk identifier', async () => {
  render(<App />); await openAssistant(); const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: /battery-operated/i }));
  expect(await screen.findByText('manual.pdf')).toBeInTheDocument();
  expect(screen.getByText('Page 4')).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent('internal');
  await user.click(screen.getByRole('button', { name: /view evidence/i }));
  expect(screen.getByText('IS 15644 applies.')).toBeInTheDocument();
});

it('refreshes answers by language, caches variants, and ignores stale localization results', async () => {
  let resolveHindi!: (value: unknown) => void;
  let resolveMarathi!: (value: unknown) => void;
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.includes('health')) return Promise.resolve(response({ status: 'ready' }));
    const language = JSON.parse(String(init?.body)).response_language;
    if (language === 'en') return Promise.resolve(response({ ...answer, answer: 'English answer.' }));
    if (language === 'hi') return new Promise(resolve => { resolveHindi = resolve; });
    return new Promise(resolve => { resolveMarathi = resolve; });
  });
  vi.stubGlobal('fetch', fetchMock); render(<App />); await openAssistant(); const user = userEvent.setup();
  await user.type(screen.getByLabelText(/ask about a product/i), 'Original question?{Enter}'); await screen.findByText('English answer.');
  await user.selectOptions(screen.getByLabelText('Language'), 'hi');
  await user.selectOptions(screen.getByLabelText('भाषा'), 'mr');
  await act(async () => resolveMarathi(response({ ...answer, answer: 'मराठी उत्तर.' })));
  await screen.findByText('मराठी उत्तर。'.replace('。', '.'));
  await act(async () => resolveHindi(response({ ...answer, answer: 'पुराना हिंदी उत्तर।' })));
  expect(screen.queryByText('पुराना हिंदी उत्तर।')).toBeNull();
  const beforeCachedReturn = fetchMock.mock.calls.length;
  await user.selectOptions(screen.getByLabelText('भाषा'), 'mr');
  expect(fetchMock).toHaveBeenCalledTimes(beforeCachedReturn);
  expect(screen.getByText('Original question?')).toBeInTheDocument();
});

it('retains the last verified answer when a language refresh fails', async () => {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.includes('health')) return Promise.resolve(response({ status: 'ready' }));
    return JSON.parse(String(init?.body)).response_language === 'hi' ? Promise.reject(new Error('private backend body')) : Promise.resolve(response({ ...answer, answer: 'English answer.' }));
  });
  vi.stubGlobal('fetch', fetchMock); render(<App />); await openAssistant(); const user = userEvent.setup();
  await user.type(screen.getByLabelText(/ask about a product/i), 'Original question?{Enter}'); await screen.findByText('English answer.');
  await user.selectOptions(screen.getByLabelText('Language'), 'hi');
  await waitFor(() => expect(screen.getByText('English answer.')).toBeInTheDocument());
  expect(document.body).not.toHaveTextContent('private backend body');
});

it('updates the localized shell on Home and view headings', async () => {
  render(<App />);
  await screen.findByRole('status');
  const user = userEvent.setup();

  await user.selectOptions(screen.getByLabelText('Language'), 'hi');
  expect(screen.getByRole('button', { name: 'होम' })).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: 'Bandhu से पूछें' })).toHaveLength(2);

  await user.selectOptions(screen.getByLabelText('भाषा'), 'mr');
  expect(screen.getByRole('button', { name: 'मुख्यपृष्ठ' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'सहाय्यक' }));
  expect(screen.getByText('BIS Bandhu सहाय्यक')).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'मुख्यपृष्ठ' }));
  await user.selectOptions(screen.getByLabelText('भाषा'), 'ta');
  expect(screen.getByRole('button', { name: 'முகப்பு' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Home' })).not.toBeInTheDocument();

  await user.selectOptions(screen.getByLabelText('மொழி'), 'bn');
  expect(screen.getByRole('button', { name: 'হোম' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Assistant' })).not.toBeInTheDocument();
});

it('retries a failed Assistant request', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response({ status: 'ready' })).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(response(answer));
  vi.stubGlobal('fetch', fetchMock);
  render(<App />); await openAssistant();
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: /battery-operated/i }));
  await user.click(await screen.findByText('Retry'));
  expect(await screen.findByText(answer.answer)).toBeInTheDocument();
});

it('prevents duplicate requests while an Assistant request is pending', async () => {
  let resolveChat!: (value: unknown) => void;
  const fetchMock = vi.fn((url: string) => url.includes('health') ? Promise.resolve(response({ status: 'ready' })) : new Promise(resolve => { resolveChat = resolve; }));
  vi.stubGlobal('fetch', fetchMock);
  render(<App />); await openAssistant();
  const user = userEvent.setup();
  const suggestion = screen.getByRole('button', { name: /battery-operated/i });
  await user.dblClick(suggestion);
  expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(1);
  await act(async () => resolveChat(response(answer)));
  expect(await screen.findByText(answer.answer)).toBeInTheDocument();
});

it('handles malformed responses safely and renders backend HTML as text', async () => {
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(response(url.includes('health') ? { status: 'ready' } : { ...answer, answer: '<b>unsafe</b>' }))));
  render(<App />); await openAssistant();
  await userEvent.setup().click(screen.getByRole('button', { name: /battery-operated/i }));
  expect(await screen.findByText('<b>unsafe</b>')).toBeInTheDocument();
  expect(document.querySelector('.answer-text b')).toBeNull();

  cleanup(); vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(response(url.includes('health') ? { status: 'ready' } : { bad: true }))));
  render(<App />); await openAssistant();
  await userEvent.setup().click(screen.getByRole('button', { name: /battery-operated/i }));
  expect(await screen.getByRole('alert')).toHaveTextContent(/unreadable/i);
});

it('submits typed questions with Enter and includes clarification context for a selected standard', async () => {
  const context = { original_question: 'Explain the standard', expected_slots: ['standard_reference' as const], referenced_standards: ['IS 15644'] };
  const clarification = { ...answer, answer: 'Which standard?', grounded: false, needs_clarification: true, generation_mode: 'clarification' as const, citations: [], suggested_replies: ['IS 15644'], assistant_context: context };
  let calls = 0;
  const fetchMock = vi.fn((url: string, _init?: RequestInit) => Promise.resolve(response(url.includes('health') ? { status: 'ready' } : calls++ === 0 ? clarification : answer)));
  vi.stubGlobal('fetch', fetchMock);
  render(<App />); await openAssistant();
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/ask about a product/i), 'Explain the standard{Enter}');
  await user.click(await screen.findByRole('button', { name: 'IS 15644' }));
  expect(await screen.findByText(answer.answer)).toBeInTheDocument();
  const chatCall = fetchMock.mock.calls.filter(([url]) => String(url).includes('/api/chat')).at(-1);
  expect(chatCall).toBeDefined();
  const payload = JSON.parse(String((chatCall![1] as RequestInit).body));
  expect(payload.assistant_context).toEqual(context);
});

it('keeps health monitoring internal instead of displaying a public backend badge', async () => {
  for (const health of [{ status: 'ready' }, { status: 'degraded' }, null] as const) {
    cleanup();
    vi.stubGlobal('fetch', vi.fn((url: string) => url.includes('health') ? health ? Promise.resolve(response(health)) : Promise.reject(new Error('offline')) : Promise.resolve(response(answer))));
    render(<App />);
    expect(await screen.findByRole('status')).toHaveAttribute('data-health', health?.status ?? 'unavailable');
    expect(screen.queryByText(/Backend ready|Backend degraded|Backend unavailable/i)).toBeNull();
  }
});

it('opens Services without inventing a standard or making an automatic request', async () => {
  render(<App />);
  await screen.findByRole('status');
  const user = userEvent.setup();

  await user.click(screen.getByRole('contentinfo').querySelector('button:last-child') as HTMLButtonElement);
  expect(screen.getByRole('heading', { name: 'BIS Bandhu services' })).toBeInTheDocument();
  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(0);
  expect(screen.queryByText(/Illustrative cooking appliance|Demo data/i)).toBeNull();
});

it('start over clears messages and retained Assistant context', async () => {
  const clarification = { ...answer, grounded: false, needs_clarification: true, generation_mode: 'clarification' as const, citations: [], assistant_context: { original_question: 'What applies?', expected_slots: ['power_type' as const] } };
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(response(url.includes('health') ? { status: 'ready' } : clarification))));
  render(<App />); await openAssistant();
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: /battery-operated/i }));
  await screen.findByText('Need more details', { selector: '.answer-status' });
  await user.click(screen.getByRole('button', { name: 'Start over' }));
  expect(screen.queryByText('Need more details', { selector: '.answer-status' })).toBeNull();
});

it('clears retained clarification context after leaving Assistant without clearing messages or Wizard answers', async () => {
  const context = { original_question: 'Explain the standard', expected_slots: ['standard_reference' as const], referenced_standards: ['IS 15644'] };
  const clarification = { ...answer, answer: 'Which standard?', grounded: false, needs_clarification: true, generation_mode: 'clarification' as const, citations: [], assistant_context: context };
  let calls = 0;
  const fetchMock = vi.fn((url: string, _init?: RequestInit) => Promise.resolve(response(url.includes('health') ? { status: 'ready' } : calls++ === 0 ? clarification : answer)));
  vi.stubGlobal('fetch', fetchMock);
  render(<App />); await openAssistant();
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/ask about a product/i), 'Explain the standard{Enter}');
  await screen.findByText('Need more details', { selector: '.answer-status' });
  await user.click(screen.getByRole('button', { name: 'Home' }));
  await user.click(screen.getByRole('button', { name: 'Assistant' }));
  expect(screen.getByText('Which standard?')).toBeInTheDocument();
  await user.type(screen.getByLabelText(/ask about a product/i), 'What should I check before buying a toy?{Enter}');
  const chatCall = fetchMock.mock.calls.filter(([url]) => String(url).includes('/api/chat')).at(-1);
  expect(chatCall).toBeDefined();
  const payload = JSON.parse(String((chatCall![1] as RequestInit).body));
  expect(payload).not.toHaveProperty('assistant_context');
});

it('clears retained context when the suggested Wizard action leaves Assistant', async () => {
  const context = { original_question: 'Explain the standard', expected_slots: ['standard_reference' as const], referenced_standards: ['IS 15644'] };
  const clarification = { ...answer, answer: 'Which standard?', grounded: false, needs_clarification: true, generation_mode: 'clarification' as const, citations: [], suggested_replies: ['Show my complete compliance roadmap'], assistant_context: context };
  let calls = 0;
  const fetchMock = vi.fn((url: string, _init?: RequestInit) => Promise.resolve(response(url.includes('health') ? { status: 'ready' } : calls++ === 0 ? clarification : answer)));
  vi.stubGlobal('fetch', fetchMock);
  render(<App />); await openAssistant();
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/ask about a product/i), 'Explain the standard{Enter}');
  await user.click(await screen.findByRole('button', { name: 'Show my complete compliance roadmap' }));
  expect(screen.getByRole('heading', { name: 'Compliance Wizard' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Assistant' }));
  expect(screen.getByText('Which standard?')).toBeInTheDocument();
  await user.type(screen.getByLabelText(/ask about a product/i), 'What should I check before buying a toy?{Enter}');
  const chatCall = fetchMock.mock.calls.filter(([url]) => String(url).includes('/api/chat')).at(-1);
  expect(chatCall).toBeDefined();
  expect(JSON.parse(String((chatCall![1] as RequestInit).body))).not.toHaveProperty('assistant_context');
});

it('shows a visible accessible theme action and switches in both directions', async () => {
  render(<App />); await screen.findByRole('status');
  const user = userEvent.setup();
  const toggle = screen.getByRole('button', { name: 'Dark mode' });
  expect(toggle).toHaveTextContent('Dark mode');
  expect(toggle).toHaveAttribute('aria-pressed', 'false');
  await user.click(toggle);
  expect(document.documentElement.dataset.theme).toBe('dark');
  expect(screen.getByRole('button', { name: 'Light mode' })).toHaveAttribute('aria-pressed', 'true');
  await user.click(screen.getByRole('button', { name: 'Light mode' }));
  expect(document.documentElement.dataset.theme).toBe('light');
  expect(screen.getByRole('button', { name: 'Dark mode' })).toHaveAttribute('aria-pressed', 'false');
});

it('always initializes light despite stored and system dark preferences', async () => {
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
  localStorage.setItem('bis-bandhu-theme', 'dark');
  render(<App />);
  await screen.findByRole('status');

  expect(document.documentElement.dataset.theme).toBe('light');
  expect(screen.getByRole('button', { name: 'Dark mode' })).toHaveAttribute('aria-pressed', 'false');
  expect(localStorage.getItem('bis-bandhu-theme')).toBe('dark');
});

it('keeps one Assistant nav item active across audience changes without losing a typed draft', async () => {
  render(<App />);
  await openAssistant();
  const user = userEvent.setup();
  const question = screen.getByLabelText('Ask about a product, standard or BIS process');

  await user.type(question, 'My unfinished product question');
  await user.selectOptions(screen.getByLabelText('I am a:'), 'manufacturer');

  expect(question).toHaveFocus();
  expect(question).toHaveValue('My unfinished product question');
  expect(screen.getByLabelText('I am a:')).toHaveValue('manufacturer');
  expect(screen.getByRole('button', { name: 'Assistant' })).toHaveAttribute('aria-current', 'page');
  expect(within(screen.getByRole('navigation')).queryAllByRole('button', { current: 'page' })).toHaveLength(1);
  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(0);

  await user.type(question, '{Enter}');
  const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(([url]) => String(url).includes('/api/chat'));
  const payload = JSON.parse(String((call?.[1] as RequestInit).body));
  expect(payload).toMatchObject({ question: 'My unfinished product question', audience: 'manufacturer' });
});

it('clears clarification context when changing audience without clearing visible history', async () => {
  const context = { original_question: 'Explain the standard', expected_slots: ['standard_reference' as const] };
  const clarification = { ...answer, answer: 'Which standard?', grounded: false, needs_clarification: true, generation_mode: 'clarification' as const, citations: [], assistant_context: context };
  let calls = 0;
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(response(url.includes('health') ? { status: 'ready' } : calls++ === 0 ? clarification : answer))));
  render(<App />);
  await openAssistant();
  const user = userEvent.setup();

  await user.type(screen.getByLabelText('Ask about a product, standard or BIS process'), 'Explain the standard{Enter}');
  await screen.findByText('Which standard?');
  await user.selectOptions(screen.getByLabelText('I am a:'), 'consumer');
  expect(screen.getByText('Which standard?')).toBeInTheDocument();
  await user.type(screen.getByLabelText('Ask about a product, standard or BIS process'), 'What should I check before buying a toy?{Enter}');

  const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat')).at(-1);
  const payload = JSON.parse(String((call?.[1] as RequestInit).body));
  expect(payload).toMatchObject({ audience: 'consumer', question: 'What should I check before buying a toy?' });
  expect(payload).not.toHaveProperty('assistant_context');
});

it('localizes consumer service and theme controls in every supported shell language', async () => {
  const labels = {
    en: ['Official BIS consumer information ↗', 'Dark mode'],
    hi: ['आधिकारिक BIS उपभोक्ता जानकारी ↗', 'गहरी थीम'],
    mr: ['अधिकृत BIS ग्राहक माहिती ↗', 'गडद मोड'],
    ta: ['அதிகாரப்பூர்வ BIS நுகர்வோர் தகவல் ↗', 'இருண்ட தோற்றம்'],
    bn: ['সরকারি BIS ভোক্তা তথ্য ↗', 'গাঢ় মোড'],
  } as const;

  for (const [language, [linkLabel, themeLabel]] of Object.entries(labels)) {
    cleanup();
    localStorage.clear();
    localStorage.setItem('bis-bandhu-theme', 'dark');
    render(<App />);
    await screen.findByRole('status');
    const user = userEvent.setup();
    await user.selectOptions(document.getElementById('language') as HTMLSelectElement, language);
    await user.click(within(screen.getByRole('navigation')).getByRole('button', { name: language === 'en' ? 'Assistant' : /^(सहायक|सहाय्यक|உதவியாளர்|সহায়ক)$/ }));
    await user.selectOptions(document.getElementById('audience') as HTMLSelectElement, 'consumer');

    expect(screen.getByRole('link', { name: linkLabel })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: themeLabel })).toBeInTheDocument();
  }
});

it('sends a Finder product question through the existing Assistant request flow', async () => {
  window.location.hash = '#/industry/finder';
  render(<App />);
  await screen.findByRole('status');
  const user = userEvent.setup();

  await user.type(screen.getByLabelText('Product description'), 'battery powered product');
  await user.click(screen.getByRole('button', { name: 'Ask BIS Bandhu' }));
  expect(await screen.findByText(answer.answer)).toBeInTheDocument();
  expect(window.location.hash).toBe('#/assistant');
  const request = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(([url]) => String(url).includes('/api/chat'));
  expect(JSON.parse(String((request?.[1] as RequestInit).body))).toMatchObject({ question: 'battery powered product', audience: 'manufacturer' });

});

class MockSpeechRecognition {
  static instances: MockSpeechRecognition[] = [];
  lang = '';
  continuous = false;
  interimResults = false;
  onstart: (() => void) | null = null;
  onend: (() => void) | null = null;
  onresult: ((event: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  start = vi.fn(() => this.onstart?.());
  stop = vi.fn(() => this.onend?.());

  constructor() { MockSpeechRecognition.instances.push(this); }
}

function mockSpeechRecognition() {
  MockSpeechRecognition.instances = [];
  Object.defineProperty(window, 'webkitSpeechRecognition', { configurable: true, value: MockSpeechRecognition });
}

it('inserts a final Home transcript after the typed draft without submitting it', async () => {
  mockSpeechRecognition();
  render(<App />); await screen.findByRole('status');
  const user = userEvent.setup();
  const input = screen.getByLabelText('Ask about a product, standard or BIS process');
  await user.type(input, 'My product is');
  await user.click(screen.getByRole('button', { name: 'Speak now' }));

  const recognition = MockSpeechRecognition.instances[0];
  expect(recognition.lang).toBe('en-IN');
  expect(screen.getByRole('button', { name: 'Stop listening' })).toHaveAttribute('aria-pressed', 'true');
  await user.click(screen.getByRole('button', { name: 'Stop listening' }));
  expect(recognition.stop).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole('button', { name: 'Speak now' }));
  const resumed = MockSpeechRecognition.instances[1];
  await act(async () => {
    resumed.onresult?.({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: ' a battery-operated toy' } }] });
    resumed.onend?.();
  });

  expect(input).toHaveValue('My product is a battery-operated toy');
  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(0);
});

it('uses every selected language locale and stops a session when language changes', async () => {
  mockSpeechRecognition();
  render(<App />); await screen.findByRole('status');
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Speak now' }));
  const first = MockSpeechRecognition.instances[0];
  await user.selectOptions(screen.getByLabelText('Language'), 'hi');
  expect(first.stop).toHaveBeenCalled();

  const locales = {
    hi: ['अब बोलें', 'सुनना बंद करें', 'hi-IN'],
    mr: ['आता बोला', 'ऐकणे थांबवा', 'mr-IN'],
    ta: ['இப்போது பேசுங்கள்', 'கேட்பதை நிறுத்து', 'ta-IN'],
    bn: ['এখন বলুন', 'শোনা বন্ধ করুন', 'bn-IN'],
    en: ['Speak now', 'Stop listening', 'en-IN'],
  } as const;
  for (const [language, [startLabel, stopLabel, locale]] of Object.entries(locales)) {
    await user.selectOptions(document.getElementById('language') as HTMLSelectElement, language);
    await user.click(screen.getByRole('button', { name: startLabel }));
    expect(MockSpeechRecognition.instances.at(-1)?.lang).toBe(locale);
    await user.click(screen.getByRole('button', { name: stopLabel }));
  }
});

it('keeps typing available when voice input is unsupported or reports an error', async () => {
  render(<App />); await screen.findByRole('status');
  const user = userEvent.setup();
  const input = screen.getByLabelText('Ask about a product, standard or BIS process');
  await user.click(screen.getByRole('button', { name: 'Speak now' }));
  expect(screen.getByText('Voice input is not supported in this browser. You can continue typing.')).toBeInTheDocument();
  await user.type(input, 'I can still type');
  expect(input).toHaveValue('I can still type');

  mockSpeechRecognition();
  await user.click(screen.getByRole('button', { name: 'Speak now' }));
  await act(async () => { MockSpeechRecognition.instances[0].onerror?.({ error: 'not-allowed' }); });
  expect(screen.getByText('Microphone permission was denied. You can continue typing.')).toBeInTheDocument();
});
