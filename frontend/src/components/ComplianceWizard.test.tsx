import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { ComplianceWizard } from './ComplianceWizard';
import { printComplianceReport } from './printComplianceReport';
import { LanguageProvider } from '../i18n/LanguageContext';
import { ChatHeader } from './ChatHeader';

const guidance = { answer: 'Grounded answer.', grounded: true, insufficient_evidence: false, evidence_count: 1, citations: [{ citation_id: 'S1', source_filename: 'manual.pdf', page_start: 4, page_end: 4, chunk_id: 'c1', excerpt: 'IS 15644 applies.' }], model: 'fake', generation_mode: 'extractive_fallback' as const, disclaimer: 'Verify.', answer_sections: [
  { type: 'direct_answer' as const, title: 'Standards found', content: 'IS 15644 applies.', items: [], citation_ids: ['S1'] },
  { type: 'explanation' as const, title: 'Reason', content: 'The evidence covers this product.', items: [], citation_ids: ['S1'] },
  { type: 'next_steps' as const, title: 'Next steps', content: null, items: ['Review the cited source.'], citation_ids: ['S1'] },
  { type: 'important' as const, title: 'Important condition', content: 'Verify before relying on guidance.', items: [], citation_ids: ['S1'] },
] };
const profile = { role: 'manufacturer', product_description: 'Toy car', power_type: 'battery_operated', intended_age_group: '3_to_8', goal: 'identify_standards', application_stage: 'researching', additional_context: null };
const response = { profile, guidance };
const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
afterEach(() => { cleanup(); localStorage.clear(); vi.restoreAllMocks(); });
const journey = () => within(screen.getByRole('region', { name: 'Compliance journey result' }));
const printReport = () => within(screen.getByRole('article', { name: 'Compliance Passport' }));

async function reachFinal(user = userEvent.setup(), role: 'Consumer' | 'Manufacturer' = 'Manufacturer', powerLabel?: string) {
  render(<ComplianceWizard />); await user.click(screen.getByRole('button', { name: role }));
  await user.type(screen.getByLabelText('Product description or type'), 'Toy car');
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  if (powerLabel) await user.click(screen.getByLabelText(powerLabel));
  for (let index = 0; index < 3; index += 1) await user.click(screen.getByRole('button', { name: 'Continue' }));
  return user;
}

function renderWizardIn(language: 'hi' | 'mr') {
  localStorage.setItem('bis-assistant-language', language);
  return render(<LanguageProvider><ComplianceWizard /></LanguageProvider>);
}

it('translates the wizard entry screen into Hindi and Marathi', () => {
  renderWizardIn('hi'); expect(screen.getByRole('heading', { name: 'अनुपालन सहायक' })).toBeInTheDocument(); expect(screen.getByRole('button', { name: 'निर्माता' })).toHaveTextContent('अनुशंसित यात्रा');
  cleanup(); renderWizardIn('mr'); expect(screen.getByRole('heading', { name: 'अनुपालन सहाय्यक' })).toBeInTheDocument(); expect(screen.getByRole('button', { name: 'उत्पादक' })).toHaveTextContent('शिफारस केलेला प्रवास');
});

it('keeps all five localized wizard steps functional and submits untranslated enum values', async () => {
  for (const [language, manufacturer, productLabel, continueLabel, powerLabel, finalHeading] of [
    ['hi', 'निर्माता', 'उत्पाद विवरण या प्रकार', 'जारी रखें', 'बैटरी से चलने वाला', 'आपको क्या चाहिए'],
    ['mr', 'उत्पादक', 'उत्पादनाचे वर्णन किंवा प्रकार', 'पुढे जा', 'बॅटरीवर चालणारे', 'तुम्हाला काय हवे आहे'],
  ] as const) {
    cleanup(); localStorage.clear(); const fetchMock = vi.fn().mockResolvedValue(ok(response)); vi.stubGlobal('fetch', fetchMock); renderWizardIn(language);
    const user = userEvent.setup(); await user.click(screen.getByRole('button', { name: manufacturer })); await user.type(screen.getByLabelText(productLabel), 'Toy car'); await user.click(screen.getByRole('button', { name: continueLabel })); await user.click(screen.getByLabelText(powerLabel));
    for (let index = 0; index < 3; index += 1) await user.click(screen.getByRole('button', { name: continueLabel }));
    expect(screen.getByRole('heading', { name: finalHeading })).toBeInTheDocument();
    const generate = language === 'hi' ? 'मेरा मार्गदर्शन बनाएँ' : 'माझे मार्गदर्शन तयार करा'; await user.click(screen.getByRole('button', { name: generate })); await screen.findAllByText('IS 15644 applies.');
    const payload = JSON.parse(String(fetchMock.mock.calls[0][1].body)); expect(payload.power_type).toBe('battery_operated'); expect(payload.response_language).toBe(language);
  }
});

it('uses the selected language in the printable report while preserving citations and standards', async () => {
  localStorage.setItem('bis-assistant-language', 'hi'); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(response))); render(<LanguageProvider><ComplianceWizard /></LanguageProvider>);
  const user = userEvent.setup(); await user.click(screen.getByRole('button', { name: 'निर्माता' })); await user.type(screen.getByLabelText('उत्पाद विवरण या प्रकार'), 'Toy car'); await user.click(screen.getByRole('button', { name: 'जारी रखें' })); for (let index = 0; index < 3; index += 1) await user.click(screen.getByRole('button', { name: 'जारी रखें' })); await user.click(screen.getByRole('button', { name: 'मेरा मार्गदर्शन बनाएँ' }));
  const report = within(await screen.findByRole('article', { name: 'अनुपालन पासपोर्ट' })); expect(report.getByRole('heading', { name: 'अनुपालन पासपोर्ट' })).toBeInTheDocument(); expect(report.getByRole('heading', { name: 'लागू मानक' })).toBeInTheDocument(); expect(report.getAllByText('IS 15644 applies.')).not.toHaveLength(0); expect(report.getAllByText(/manual\.pdf/).length).toBeGreaterThan(0); expect(screen.getAllByText('पृष्ठ 4')).not.toHaveLength(0);
});

it('preserves entered profile data when language switches during the wizard', async () => {
  render(<LanguageProvider><ChatHeader status="ready" /><ComplianceWizard /></LanguageProvider>); const user = userEvent.setup(); await user.click(screen.getByRole('button', { name: 'Manufacturer' })); await user.type(screen.getByLabelText('Product description or type'), 'Toy car'); await user.selectOptions(screen.getByLabelText('Language'), 'mr'); expect(screen.getByLabelText('उत्पादनाचे वर्णन किंवा प्रकार')).toHaveValue('Toy car');
});

it('offers clear consumer and highlighted manufacturer entry choices', async () => {
  const user = userEvent.setup(); render(<ComplianceWizard />);
  expect(screen.getByRole('button', { name: 'Consumer' })).toHaveTextContent(/before you buy/i);
  expect(screen.getByRole('button', { name: 'Manufacturer' })).toHaveTextContent(/Recommended journey/i);
  await user.click(screen.getByRole('button', { name: 'Consumer' }));
  expect(screen.getByText(/consumer journey/i)).toBeInTheDocument(); expect(screen.getByText('Step 1 of 5')).toBeInTheDocument();
});

it('runs exactly five manufacturer questions with back and review editing', async () => {
  const user = userEvent.setup(); render(<ComplianceWizard />); await user.click(screen.getByRole('button', { name: 'Manufacturer' }));
  expect(screen.getByText('Step 1 of 5')).toBeInTheDocument(); await user.type(screen.getByLabelText('Product description or type'), 'Toy car'); await user.click(screen.getByRole('button', { name: 'Continue' }));
  expect(screen.getByText('Step 2 of 5')).toBeInTheDocument(); await user.click(screen.getByRole('button', { name: 'Back' })); expect(screen.getByLabelText('Product description or type')).toHaveValue('Toy car');
  for (let index = 0; index < 4; index += 1) await user.click(screen.getByRole('button', { name: 'Continue' }));
  expect(screen.getByText('Review before generating')).toBeInTheDocument(); await user.click(screen.getByRole('button', { name: 'Edit power type' })); expect(screen.getByText('Step 2 of 5')).toBeInTheDocument();
});

it('preserves Not sure choices and does not submit them as product evidence', async () => {
  const fetchMock = vi.fn().mockResolvedValue(ok({ ...response, profile: { ...profile, power_type: 'not_sure' } })); vi.stubGlobal('fetch', fetchMock); const user = await reachFinal(userEvent.setup(), 'Manufacturer', 'Not sure');
  await user.click(screen.getByRole('button', { name: 'Generate my guidance' }));
  const body = JSON.parse(fetchMock.mock.calls[0][1].body); expect(body.power_type).toBe('not_sure'); expect(screen.queryByText('Not sure is a factual product claim')).not.toBeInTheDocument();
});

it('does not turn untrusted profile text into displayed evidence or citations', async () => {
  const untrustedText = 'Profile says IS 99999 applies without evidence.';
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ ...response, profile: { ...profile, product_description: untrustedText } })));
  const user = await reachFinal(); await user.click(screen.getByRole('button', { name: 'Generate my guidance' }));
  expect((await journey().findAllByText('IS 15644 applies.')).length).toBeGreaterThan(0); expect(journey().getByRole('region', { name: 'Your product profile' })).toHaveTextContent('Toy car'); expect(journey().queryByText(untrustedText)).not.toBeInTheDocument(); expect(journey().queryByText('IS 99999 applies.', { exact: true })).not.toBeInTheDocument(); expect(journey().getByRole('link', { name: /manual.pdf.*page 4/i })).toBeInTheDocument();
});

it('renders one coherent grounded roadmap with profile, categories, and verified sources', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(response))); const user = await reachFinal(); await user.click(screen.getByRole('button', { name: 'Generate my guidance' }));
  for (const heading of ['Your product profile', 'Applicable standards', 'Why these standards apply', 'Your compliance checklist', 'Important conditions']) expect((await journey().findAllByRole('heading', { name: heading })).length).toBeGreaterThan(0);
  expect((await journey().findAllByRole('heading', { name: /Verified sources 1/i })).length).toBeGreaterThan(0);
  expect(journey().getAllByText(/not verified BIS evidence/i).length).toBeGreaterThan(0);
  expect(journey().getAllByRole('heading', { name: /Verified sources/i }).length).toBeGreaterThan(0); expect(journey().getByRole('link', { name: /manual.pdf.*page 4/i })).toBeInTheDocument();
});

it('prints only the dedicated report in an isolated iframe without altering the screen result', async () => {
  const mainPrint = vi.spyOn(window, 'print').mockImplementation(() => undefined);
  const iframePrint = vi.fn();
  const appendToBody = document.body.append.bind(document.body);
  vi.spyOn(document.body, 'append').mockImplementation((...nodes: Array<Node | string>) => {
    appendToBody(...nodes);
    for (const node of nodes) if (node instanceof HTMLIFrameElement) Object.defineProperty(node.contentWindow!, 'print', { configurable: true, value: iframePrint });
  });
  const report = { ...response, guidance: { ...guidance, citations: [
    { ...guidance.citations[0], excerpt: 'Raw evidence excerpt S1', page_start: 4, page_end: 4 }, { ...guidance.citations[0], excerpt: 'Raw evidence excerpt S1', citation_id: 'S2', chunk_id: 'c2', page_start: 3, page_end: 3 }, { ...guidance.citations[0], excerpt: 'Raw evidence excerpt S1', citation_id: 'S3', chunk_id: 'c3', page_start: 4, page_end: 4 }, { ...guidance.citations[0], excerpt: 'Raw evidence excerpt S1', citation_id: 'S4', chunk_id: 'c4', source_filename: 'certification.pdf', page_start: 5, page_end: 5 },
  ], answer_sections: [...guidance.answer_sections, { type: 'explanation' as const, title: 'Your profile', content: 'Duplicate profile narrative.', items: [], citation_ids: [] }, { type: 'explanation' as const, title: 'Certification position', content: 'Duplicate stage narrative.', items: [], citation_ids: [] }, { type: 'next_steps' as const, title: 'Your next action', content: null, items: ['Open the cited primary standard.'], citation_ids: ['S1'] }] } };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(report))); const user = await reachFinal(); await user.click(screen.getByRole('button', { name: 'Generate my guidance' }));
  expect(await screen.findByRole('button', { name: 'Save compliance passport as PDF or print' })).toBeInTheDocument();
  const reportView = printReport();
  for (const text of ['Compliance Passport', 'Toy car', 'IS 15644 applies.', 'The evidence covers this product.', 'Review the cited source.', 'Open the cited primary standard.', 'Verify before relying on guidance.', 'Informational guidance — not a BIS certificate.']) expect(reportView.getAllByText(text).length).toBeGreaterThan(0);
  expect(reportView.getByText(/BIS-CP-/)).toBeInTheDocument(); expect(reportView.getByRole('heading', { name: 'Product profile' })).toBeInTheDocument(); expect(reportView.getByRole('heading', { name: 'Applicable standards' })).toBeInTheDocument(); expect(reportView.getByRole('heading', { name: 'Evidence-backed completed findings' })).toBeInTheDocument(); expect(reportView.getByRole('heading', { name: 'Cited evidence' })).toBeInTheDocument();
  expect(reportView.getAllByText(/manual\.pdf/).length).toBeGreaterThan(0); expect(reportView.queryByText(/certification\.pdf/)).not.toBeInTheDocument(); expect(reportView.getAllByText('Raw evidence excerpt S1').length).toBeGreaterThan(0);
  const root = document.getElementById('root') ?? document.body.firstElementChild as HTMLElement; const rootClass = root.className; const bodyClass = document.body.className; const htmlClass = document.documentElement.className; const rootStyle = root.getAttribute('style'); const bodyStyle = document.body.getAttribute('style'); const htmlStyle = document.documentElement.getAttribute('style');
  const button = screen.getByRole('button', { name: 'Save compliance passport as PDF or print' });
  const unrelatedContent = document.createTextNode('Powered by Netlify unrelated body content'); document.body.append(unrelatedContent);
  await user.click(button);
  const frame = await waitFor(() => {
    const next = document.querySelector<HTMLIFrameElement>('iframe.compliance-print-frame');
    expect(next).not.toBeNull();
    return next!;
  });
  await waitFor(() => expect(iframePrint).toHaveBeenCalledTimes(1));
  expect(mainPrint).not.toHaveBeenCalled();
  expect(iframePrint.mock.contexts[0]).toBe(frame.contentWindow);
  const printed = frame.contentDocument!;
  expect(printed.querySelector('.compliance-print-report')).not.toBeNull(); expect(printed.querySelector('.journey-result')).toBeNull(); expect(printed.querySelector('nav')).toBeNull(); expect(printed.body).not.toHaveTextContent('Powered by Netlify'); expect(printed.body).not.toHaveTextContent('unrelated body content');
  expect(root.className).toBe(rootClass); expect(document.body.className).toBe(bodyClass); expect(document.documentElement.className).toBe(htmlClass); expect(root.getAttribute('style')).toBe(rootStyle); expect(document.body.getAttribute('style')).toBe(bodyStyle); expect(document.documentElement.getAttribute('style')).toBe(htmlStyle); expect((await journey().findAllByRole('heading', { name: 'Applicable standards' })).length).toBeGreaterThan(0);
  act(() => frame.contentWindow!.dispatchEvent(new Event('afterprint')));
  await waitFor(() => expect(document.querySelector('iframe.compliance-print-frame')).toBeNull()); expect(document.activeElement).toBe(button);
  await user.click(button);
  const secondFrame = await waitFor(() => {
    const next = document.querySelector<HTMLIFrameElement>('iframe.compliance-print-frame');
    expect(next).not.toBeNull();
    return next!;
  });
  await waitFor(() => expect(iframePrint).toHaveBeenCalledTimes(2));
  expect(iframePrint.mock.contexts[1]).toBe(secondFrame.contentWindow);
  act(() => secondFrame.contentWindow!.dispatchEvent(new Event('afterprint')));
  await waitFor(() => expect(document.querySelectorAll('iframe.compliance-print-frame')).toHaveLength(0));
  unrelatedContent.remove();
});

it('does not offer a report for ungrounded or clarification guidance', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ ...response, guidance: { ...guidance, grounded: false, insufficient_evidence: true } }))); const user = await reachFinal(); await user.click(screen.getByRole('button', { name: 'Generate my guidance' }));
  expect(await screen.findByText('Evidence insufficient')).toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Save compliance passport as PDF or print' })).not.toBeInTheDocument(); expect(screen.queryByRole('region', { name: 'Compliance Passport' })).not.toBeInTheDocument();
});

it('uses a bounded, idempotent fallback to remove an abandoned print iframe', async () => {
  vi.useFakeTimers();
  const report = document.createElement('article'); report.className = 'compliance-print-report'; report.textContent = 'Only report content';
  const origin = document.createElement('button'); document.body.append(origin);
  const appendToBody = document.body.append.bind(document.body); const iframePrint = vi.fn();
  vi.spyOn(document.body, 'append').mockImplementation((...nodes: Array<Node | string>) => {
    appendToBody(...nodes);
    for (const node of nodes) if (node instanceof HTMLIFrameElement) {
      Object.defineProperty(node.contentWindow!, 'print', { configurable: true, value: iframePrint });
      Object.defineProperty(node.contentWindow!, 'focus', { configurable: true, value: vi.fn() });
    }
  });
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => window.setTimeout(() => callback(0), 1));
  printComplianceReport(report, origin);
  await Promise.resolve(); await vi.advanceTimersByTimeAsync(1);
  expect(iframePrint).toHaveBeenCalledTimes(1); expect(document.querySelectorAll('iframe.compliance-print-frame')).toHaveLength(1);
  await vi.advanceTimersByTimeAsync(30000);
  expect(document.querySelectorAll('iframe.compliance-print-frame')).toHaveLength(0);
  await vi.advanceTimersByTimeAsync(30000);
  expect(document.querySelectorAll('iframe.compliance-print-frame')).toHaveLength(0);
  vi.useRealTimers();
  origin.remove();
});

it('does not offer a report while loading, during review, or after a request error', async () => {
  let reject!: (reason: Error) => void; vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise((_, fail) => { reject = fail; }))); const user = await reachFinal();
  expect(screen.queryByRole('button', { name: 'Save compliance passport as PDF or print' })).not.toBeInTheDocument(); await user.click(screen.getByRole('button', { name: 'Generate my guidance' })); expect(screen.queryByRole('button', { name: 'Save compliance passport as PDF or print' })).not.toBeInTheDocument(); await act(async () => reject(new Error('offline'))); expect(await screen.findByRole('alert')).toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Save compliance passport as PDF or print' })).not.toBeInTheDocument();
});

it('renders battery, mains-powered and non-electric guidance through the same grounded result path', async () => {
  for (const power_type of ['battery_operated', 'mains_electric', 'non_electric']) {
    cleanup(); vi.restoreAllMocks(); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ ...response, profile: { ...profile, power_type } }))); const user = await reachFinal(userEvent.setup(), 'Manufacturer', power_type === 'battery_operated' ? undefined : power_type === 'mains_electric' ? 'Mains-powered' : 'Non-electric');
    await user.click(screen.getByRole('button', { name: 'Generate my guidance' })); expect((await journey().findAllByRole('heading', { name: 'Applicable standards' })).length).toBeGreaterThan(0);
  }
});

it('prevents duplicate submission, exposes retry, and starts over', async () => {
  let resolve!: (value: unknown) => void; const pending = new Promise(value => { resolve = value; }); const fetchMock = vi.fn().mockReturnValueOnce(pending).mockRejectedValueOnce(new Error('offline')); vi.stubGlobal('fetch', fetchMock); const user = await reachFinal();
  await user.click(screen.getByRole('button', { name: 'Generate my guidance' })); await user.click(screen.getByRole('button', { name: /Preparing grounded guidance/ })); expect(fetchMock).toHaveBeenCalledTimes(1);
  await act(async () => resolve({ ok: false, status: 503, json: async () => ({}) })); await user.click(await screen.findByRole('button', { name: 'Retry' })); expect(fetchMock).toHaveBeenCalledTimes(2); await user.click(screen.getByRole('button', { name: 'Start over' })); expect(screen.getByRole('button', { name: 'Consumer' })).toBeInTheDocument();
});

it('shows a friendly clarification without an empty roadmap and supports editing the requested answer', async () => {
  const clarification = { ...response, guidance: { ...guidance, answer: 'Which power source does the toy use?', grounded: false, insufficient_evidence: false, needs_clarification: true, generation_mode: 'clarification' as const, citations: [], answer_sections: [{ type: 'clarification' as const, title: 'Need power type', content: 'Which power source does the toy use?', items: [], citation_ids: [] }], assistant_context: { expected_slots: ['power_type'] } } };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(clarification))); const user = await reachFinal(); await user.click(screen.getByRole('button', { name: 'Generate my guidance' }));
  expect(await screen.findByRole('heading', { name: 'We need one more detail' })).toBeInTheDocument(); expect(screen.queryByText('Your personalized checklist and next action')).not.toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Save compliance passport as PDF or print' })).not.toBeInTheDocument(); expect(screen.queryByRole('region', { name: 'Compliance Passport' })).not.toBeInTheDocument(); await user.click(screen.getByRole('button', { name: 'Edit this answer' })); expect(screen.getByText('Step 2 of 5')).toBeInTheDocument();
});

it('is keyboard-accessible and aborts an active request on unmount', async () => {
  const user = userEvent.setup(); render(<ComplianceWizard />); await user.keyboard('{Tab}{Enter}'); expect(screen.getByText(/consumer journey/i)).toBeInTheDocument(); cleanup();
  let captured: AbortSignal | undefined; vi.stubGlobal('fetch', vi.fn((_url, init) => { captured = init?.signal; return new Promise(() => undefined); })); const manufacturer = await reachFinal(); await manufacturer.click(screen.getByRole('button', { name: 'Generate my guidance' })); cleanup(); await waitFor(() => expect(captured?.aborted).toBe(true));
});

it('refreshes a generated result without resetting the typed profile', async () => {
 const localized = { ...response, guidance: { ...guidance, answer: 'मराठी मार्गदर्शन.', answer_sections: [{ ...guidance.answer_sections[0], content: 'मराठी मार्गदर्शन.' }, ...guidance.answer_sections.slice(1)] } };
 const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
  const body = JSON.parse(String(init?.body)); return Promise.resolve(ok(body.response_language === 'mr' ? localized : response));
 });
 vi.stubGlobal('fetch', fetchMock); render(<LanguageProvider><ChatHeader status="ready" /><ComplianceWizard /></LanguageProvider>);
 const user = userEvent.setup(); await user.click(screen.getByRole('button', { name: 'Manufacturer' })); await user.type(screen.getByLabelText('Product description or type'), 'Toy car'); await user.click(screen.getByRole('button', { name: 'Continue' }));
 for (let index = 0; index < 3; index += 1) await user.click(screen.getByRole('button', { name: 'Continue' })); await user.click(screen.getByRole('button', { name: 'Generate my guidance' })); await screen.findAllByText('IS 15644 applies.');
 const englishPassport = within(await screen.findByRole('region', { name: 'Compliance Passport' })); const reportId = englishPassport.getByText(/BIS-CP-/).textContent; const generated = englishPassport.getByRole('time').getAttribute('datetime');
 await user.selectOptions(screen.getByLabelText('Language'), 'mr'); await screen.findAllByText('मराठी मार्गदर्शन.'); expect(screen.getAllByText('Toy car')).not.toHaveLength(0); const marathiPassport = within(await screen.findByRole('region', { name: 'अनुपालन पासपोर्ट' })); expect(marathiPassport.getByText(/BIS-CP-/)).toHaveTextContent(reportId ?? ''); expect(marathiPassport.getByRole('time')).toHaveAttribute('datetime', generated ?? '');
 const localizationCall = fetchMock.mock.calls[1]; const localizationPayload = JSON.parse(String((localizationCall?.[1] as RequestInit | undefined)?.body)); expect(localizationPayload.response_language).toBe('mr'); expect(localizationPayload.power_type).toBe('not_sure');
});
