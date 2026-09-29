import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from './App';

const answer = { answer: 'IS 15644 is the primary standard.', grounded: true, insufficient_evidence: false, evidence_count: 1, citations: [{ citation_id: 'S1', source_filename: 'manual.pdf', page_start: 4, page_end: 4, chunk_id: 'internal', excerpt: 'IS 15644 applies.' }], model: 'test', generation_mode: 'llm' as const, disclaimer: 'Verify.' };
const response = (body: unknown) => ({ ok: true, json: async () => body });

beforeEach(() => { localStorage.clear(); vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(response(url.includes('health') ? { status: 'ready' } : answer)))); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

async function openAssistant() {
  await screen.findByRole('status');
  await userEvent.setup().click(screen.getByRole('button', { name: 'Assistant' }));
}

it('opens on the BIS Bandhu homepage with working journeys', async () => {
  render(<App />); await screen.findByRole('status');
  expect(screen.getByRole('heading', { name: /Indian Standards, made clearer/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Find a Standard' })).toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole('button', { name: /Create a Compliance Passport/ }));
  expect(screen.getByText('BIS Bandhu · Compliance Passport')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Compliance Wizard' })).toBeInTheDocument();
});

it('sends the example request only from its explicit action', async () => {
  render(<App />); await screen.findByRole('status');
  await userEvent.setup().click(screen.getByRole('button', { name: 'Try an example' }));
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
  expect(screen.getByLabelText(/BIS खिलौना मानक/i)).toBeInTheDocument();
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
  expect(screen.getByLabelText('Ask a question about BIS toy standards')).toHaveFocus();
});

it('opens the Industry card as an editable Manufacturer journey without a chat request', async () => {
  render(<App />);
  await screen.findByRole('status');
  await userEvent.setup().click(screen.getByRole('button', { name: /For industry/ }));

  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(0);
  expect(screen.getByLabelText('I am a:')).toHaveValue('manufacturer');
  expect(screen.getByLabelText('Ask a question about BIS toy standards')).toHaveFocus();
});

it('opens the Consumer card as an editable Consumer journey without a chat request', async () => {
  render(<App />);
  await screen.findByRole('status');
  await userEvent.setup().click(screen.getByRole('button', { name: /For consumers/ }));

  expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).includes('/api/chat'))).toHaveLength(0);
  expect(screen.getByLabelText('I am a:')).toHaveValue('consumer');
  expect(screen.getByLabelText('Ask a question about BIS toy standards')).toHaveFocus();
});

it('submits the customer product wording as a Manufacturer and renders API evidence', async () => {
  const apiAnswer = { ...answer, answer: 'Mocked product guidance from the backend.', citations: [{ ...answer.citations[0], source_filename: 'mocked-guidance.pdf', excerpt: 'Mocked source excerpt.' }] };
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(response(url.includes('health') ? { status: 'ready' } : apiAnswer))));
  render(<App />);
  await screen.findByRole('status');
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Find a Standard' }));
  await user.type(screen.getByLabelText('Ask a question about BIS toy standards'), 'What standard applies to my wooden puzzle?{Enter}');

  expect(await screen.findByText('Mocked product guidance from the backend.')).toBeInTheDocument();
  expect(screen.getByText('mocked-guidance.pdf')).toBeInTheDocument();
  expect(screen.queryByText('Mocked source excerpt.')).not.toBeInTheDocument();
  const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(([url]) => String(url).includes('/api/chat'));
  const payload = JSON.parse(String((call?.[1] as RequestInit).body));
  expect(payload.question).toBe('What standard applies to my wooden puzzle?');
  expect(payload.audience).toBe('manufacturer');
  expect(payload.question).not.toContain('battery-operated');
});

it('keeps the battery-operated toy request behind the explicit example action', async () => {
  render(<App />);
  await screen.findByRole('status');
  await userEvent.setup().click(screen.getByRole('button', { name: 'Try an example' }));
  const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.find(([url]) => String(url).includes('/api/chat'));
  expect(JSON.parse(String((call?.[1] as RequestInit).body)).question).toBe('Which standard applies to a battery-operated toy?');
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
  await user.type(screen.getByLabelText(/ask a question/i), 'Original question?{Enter}'); await screen.findByText('English answer.');
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
  await user.type(screen.getByLabelText(/ask a question/i), 'Original question?{Enter}'); await screen.findByText('English answer.');
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
  await user.type(screen.getByLabelText(/ask a question/i), 'Explain the standard{Enter}');
  await user.click(await screen.findByRole('button', { name: 'IS 15644' }));
  expect(await screen.findByText(answer.answer)).toBeInTheDocument();
  const chatCall = fetchMock.mock.calls.filter(([url]) => String(url).includes('/api/chat')).at(-1);
  expect(chatCall).toBeDefined();
  const payload = JSON.parse(String((chatCall![1] as RequestInit).body));
  expect(payload.assistant_context).toEqual(context);
});

it('reports ready, degraded, and unavailable health states', async () => {
  for (const health of [{ status: 'ready' }, { status: 'degraded' }, null] as const) {
    cleanup();
    vi.stubGlobal('fetch', vi.fn((url: string) => url.includes('health') ? health ? Promise.resolve(response(health)) : Promise.reject(new Error('offline')) : Promise.resolve(response(answer))));
    render(<App />);
    expect(await screen.findByRole('status')).toHaveTextContent(health?.status ?? 'unavailable');
  }
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
  await user.type(screen.getByLabelText(/ask a question/i), 'Explain the standard{Enter}');
  await screen.findByText('Need more details', { selector: '.answer-status' });
  await user.click(screen.getByRole('button', { name: 'Home' }));
  await user.click(screen.getByRole('button', { name: 'Assistant' }));
  expect(screen.getByText('Which standard?')).toBeInTheDocument();
  await user.type(screen.getByLabelText(/ask a question/i), 'What should I check before buying a toy?{Enter}');
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
  await user.type(screen.getByLabelText(/ask a question/i), 'Explain the standard{Enter}');
  await user.click(await screen.findByRole('button', { name: 'Show my complete compliance roadmap' }));
  expect(screen.getByRole('heading', { name: 'Compliance Wizard' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Assistant' }));
  expect(screen.getByText('Which standard?')).toBeInTheDocument();
  await user.type(screen.getByLabelText(/ask a question/i), 'What should I check before buying a toy?{Enter}');
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

it('focuses the existing draft on audience navigation, exposes one active item, and makes no automatic request', async () => {
  render(<App />);
  await openAssistant();
  const user = userEvent.setup();
  const question = screen.getByLabelText('Ask a question about BIS toy standards');

  await user.type(question, 'My unfinished product question');
  await user.click(screen.getByRole('button', { name: 'Industry' }));

  expect(question).toHaveFocus();
  expect(question).toHaveValue('My unfinished product question');
  expect(screen.getByLabelText('I am a:')).toHaveValue('manufacturer');
  expect(screen.getByRole('button', { name: 'Industry' })).toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('button', { name: 'Assistant' })).not.toHaveAttribute('aria-current');
  expect(screen.getByRole('button', { name: 'Consumers' })).not.toHaveAttribute('aria-current');
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

  await user.type(screen.getByLabelText('Ask a question about BIS toy standards'), 'Explain the standard{Enter}');
  await screen.findByText('Which standard?');
  await user.selectOptions(screen.getByLabelText('I am a:'), 'consumer');
  expect(screen.getByText('Which standard?')).toBeInTheDocument();
  await user.type(screen.getByLabelText('Ask a question about BIS toy standards'), 'What should I check before buying a toy?{Enter}');

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
    await user.click(within(screen.getByRole('navigation')).getByRole('button', { name: language === 'en' ? 'Consumers' : /उपभोक्ता|ग्राहक|நுகர்வோர்|ভোক্তা/ }));

    expect(screen.getByRole('link', { name: linkLabel })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: themeLabel })).toBeInTheDocument();
  }
});
