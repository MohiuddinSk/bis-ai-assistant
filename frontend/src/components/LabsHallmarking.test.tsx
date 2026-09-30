import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { LanguageProvider, useLanguage } from '../i18n/LanguageContext';
import { HallmarkingPage, TestingLabsPage } from './LabsHallmarking';
import { searchLaboratories } from '../services/api';
import type { LaboratoryCapability } from '../types/catalogue';

vi.mock('../services/api', () => ({ searchLaboratories: vi.fn() }));

const lab = (id: string, name: string, location: string) => ({
  id, code: id, name, location, state: location, official_url: 'https://lims.bis.gov.in/home/labs/',
  directory_valid_until: '2027-01-01', recognition_status: null, lab_type: null,
  retrieved_at: '2026-09-30T04:00:00+00:00', provenance: 'BIS LIMS directory',
});
const scope: LaboratoryCapability = {
  id: 'scope-1', laboratory_id: 'LAB-1', standard_identifier: 'IS 4151:2015',
  product_title: 'Protective helmets', grade_type: 'Type A', testing_facility: null,
  exclusions: null, scope_valid_until: null, search_validity_date: '2027-01-01',
  charge_amount: '14000', charge_currency: 'INR', charge_basis: 'LIMS listed scope-row amount',
  tax_treatment: 'Excluding taxes', charge_note: 'Additional tests separately listed',
  effective_date: null, remarks: null, source_url: 'https://lims.bis.gov.in/home/search_is_number/?is_number__doc_no=4151',
  retrieved_at: '2026-09-30T04:00:00+00:00', provenance: 'BIS LIMS IS search',
};
const response = (query: string, results: Array<{laboratory: ReturnType<typeof lab>; capabilities: Array<typeof scope>}>, total = results.length, page = 1) => ({
  query, results, laboratory_count: 441, capability_count: 362, total_matches: total,
  page, page_size: 20, last_updated: '2026-09-30T04:00:00+00:00', coverage_note: 'Bounded dated snapshot',
});

afterEach(() => { cleanup(); localStorage.clear(); vi.clearAllMocks(); });

it('searches the API-backed lab snapshot, shows exact scope/price/source and keeps official handoff', async () => {
  vi.mocked(searchLaboratories).mockImplementation(async (query) => query === 'IS 4151'
    ? response(query, [{laboratory: lab('LAB-1', 'PRESTO LABORATORIES PRIVATE LIMITED', 'Delhi'), capabilities: [scope]}])
    : query === 'Noida'
      ? response(query, [{laboratory: lab('LAB-2', 'Testtex India Laboratories Private Limited', 'Noida'), capabilities: [{...scope, id: 'scope-2', laboratory_id: 'LAB-2', charge_amount: null, charge_currency: null}]}])
      : query === 'IS 99999' ? response(query, [])
      : response('', [{laboratory: lab('LAB-1', 'PRESTO LABORATORIES PRIVATE LIMITED', 'Delhi'), capabilities: [scope]}, {laboratory: lab('LAB-2', 'Testtex India Laboratories Private Limited', 'Noida'), capabilities: []}], 441));
  render(<LanguageProvider><TestingLabsPage /></LanguageProvider>);
  const user = userEvent.setup();
  expect(await screen.findByText(/441 laboratories/)).toBeInTheDocument();
  expect(screen.getByText('PRESTO LABORATORIES PRIVATE LIMITED')).toBeInTheDocument();
  expect(screen.getByText('Testtex India Laboratories Private Limited')).toBeInTheDocument();
  await user.type(screen.getByLabelText('IS number, product, laboratory or location'), 'IS 4151');
  await user.click(screen.getByRole('button', { name: 'Search checked records' }));
  await waitFor(() => expect(searchLaboratories).toHaveBeenLastCalledWith('IS 4151', 1, expect.any(AbortSignal)));
  expect(await screen.findByText('PRESTO LABORATORIES PRIVATE LIMITED')).toBeInTheDocument();
  expect(screen.queryByText('Testtex India Laboratories Private Limited')).toBeNull();
  expect(screen.getByText('₹14,000')).toBeInTheDocument();
  expect(screen.getByText('IS 4151:2015')).toBeInTheDocument();
  expect(screen.getByText('LIMS search validity date')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Check this record in BIS LIMS ↗' })).toHaveAttribute('href', scope.source_url);
  expect(screen.getByRole('link', { name: 'Search current IS scope and testing charges in BIS LIMS ↗' })).toHaveAttribute('href', 'https://lims.bis.gov.in/home/search_is_number/?is_number__doc_no=4151');
  await user.clear(screen.getByLabelText('IS number, product, laboratory or location'));
  await user.type(screen.getByLabelText('IS number, product, laboratory or location'), 'Noida');
  await user.click(screen.getByRole('button', { name: 'Search checked records' }));
  expect(await screen.findByText('Testtex India Laboratories Private Limited')).toBeInTheDocument();
  expect(screen.getByText(/Price not published/)).toBeInTheDocument();
  await user.clear(screen.getByLabelText('IS number, product, laboratory or location'));
  await user.type(screen.getByLabelText('IS number, product, laboratory or location'), 'IS 99999');
  await user.click(screen.getByRole('button', { name: 'Search checked records' }));
  expect(await screen.findByText(/This does not mean BIS LIMS has no suitable lab/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Search current IS scope and testing charges in BIS LIMS ↗' })).toHaveAttribute('href', 'https://lims.bis.gov.in/home/search_is_number/?is_number__doc_no=99999');
});

it('paginates laboratory identities and retains the typed query across a language change', async () => {
  vi.mocked(searchLaboratories).mockImplementation(async (query, page) => page === 2
    ? response(query, [{ laboratory: lab('LAB-2', 'Second official laboratory', 'Pune'), capabilities: [] }], 21, 2)
    : response(query, [{ laboratory: lab('LAB-1', 'First official laboratory', 'Delhi'), capabilities: [scope] }], 21));
  function LanguageSwitch() {
    const { setLanguage } = useLanguage();
    return <button onClick={() => setLanguage('hi')}>Hindi</button>;
  }
  render(<LanguageProvider><LanguageSwitch /><TestingLabsPage /></LanguageProvider>);
  const user = userEvent.setup();
  expect(await screen.findByText('First official laboratory')).toBeInTheDocument();
  await user.type(screen.getByLabelText('IS number, product, laboratory or location'), 'helmet');
  await user.click(screen.getByRole('button', { name: 'Search checked records' }));
  await waitFor(() => expect(searchLaboratories).toHaveBeenLastCalledWith('helmet', 1, expect.any(AbortSignal)));
  await user.click(screen.getByRole('button', { name: 'Hindi' }));
  expect(screen.getByLabelText('IS नंबर, उत्पाद, प्रयोगशाला या स्थान')).toHaveValue('helmet');
  await user.click(screen.getByRole('button', { name: 'अगला पृष्ठ' }));
  expect(await screen.findByText('Second official laboratory')).toBeInTheDocument();
  expect(screen.queryByText('First official laboratory')).toBeNull();
  expect(searchLaboratories).toHaveBeenLastCalledWith('helmet', 2, expect.any(AbortSignal));
});

it('offers retry after a laboratory source failure', async () => {
  vi.mocked(searchLaboratories).mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValueOnce(response('', [{ laboratory: lab('LAB-1', 'Recovered laboratory', 'Delhi'), capabilities: [] }]));
  render(<LanguageProvider><TestingLabsPage /></LanguageProvider>);
  expect(await screen.findByRole('alert')).toHaveTextContent('The laboratory directory could not be loaded');
  await userEvent.setup().click(screen.getByRole('button', { name: 'Retry' }));
  expect(await screen.findByText('Recovered laboratory')).toBeInTheDocument();
  expect(searchLaboratories).toHaveBeenCalledTimes(2);
});

it('checks six-character alphanumeric HUID format without an authenticity verdict or network request', async () => {
  render(<LanguageProvider><HallmarkingPage /></LanguageProvider>);
  const user = userEvent.setup();
  const huid = screen.getByLabelText('HUID printed on the article');
  await user.type(huid, 'A12');
  await user.click(screen.getByRole('button', { name: 'Check input format' }));
  expect(screen.getByText(/exactly six letters or digits/)).toBeInTheDocument();
  await user.clear(huid);
  await user.type(huid, 'ab12cd');
  await user.click(screen.getByRole('button', { name: 'Check input format' }));
  expect(huid).toHaveValue('AB12CD');
  expect(screen.getByText(/authenticity has NOT been verified/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Verify HUID in BIS Care ↗' })).toHaveAttribute('href', 'https://www.bis.gov.in/bis-apps/?lang=en');
  expect(screen.queryByText(/^HUID verified$/i)).toBeNull();
});

it('keeps suggested hallmarking questions editable until explicit submission, with the chosen audience', async () => {
  const onAsk = vi.fn();
  render(<LanguageProvider><HallmarkingPage onAsk={onAsk} /></LanguageProvider>);
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'What is HUID, and how can I verify it?' }));
  const question = screen.getByLabelText('Your hallmarking question');
  expect(question).toHaveValue('What is HUID, and how can I verify it?');
  expect(onAsk).not.toHaveBeenCalled();
  await user.type(question, ' Please explain.');
  await user.click(screen.getByRole('button', { name: 'Ask Bandhu' }));
  expect(onAsk).toHaveBeenCalledWith('What is HUID, and how can I verify it? Please explain.', 'consumer');
  await user.click(screen.getByRole('button', { name: 'How can a jeweller get started with BIS hallmarking?' }));
  expect(onAsk).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole('button', { name: 'Ask Bandhu' }));
  expect(onAsk).toHaveBeenLastCalledWith('How can a jeweller get started with BIS hallmarking?', 'manufacturer');
});

it('localizes detailed lab and HUID guidance in all five languages', () => {
  const examples = {
    en: ['Search checked records', 'Check input format'],
    hi: ['जाँचे गए रिकॉर्ड खोजें', 'इनपुट प्रारूप जाँचें'],
    mr: ['तपासलेल्या नोंदी शोधा', 'इनपुटचा नमुना तपासा'],
    ta: ['சரிபார்த்த பதிவுகளைத் தேடுக', 'உள்ளீட்டு வடிவம் சரிபார்க்கவும்'],
    bn: ['যাচাই করা রেকর্ড খুঁজুন', 'ইনপুটের ধরন পরীক্ষা'],
  };
  for (const [language, [labAction, huidAction]] of Object.entries(examples)) {
    cleanup(); localStorage.setItem('bis-assistant-language', language);
    render(<LanguageProvider><TestingLabsPage /><HallmarkingPage /></LanguageProvider>);
    expect(screen.getByRole('button', { name: labAction })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: huidAction })).toBeInTheDocument();
  }
});

it('localizes imported-directory counts and pagination in all five languages', async () => {
  vi.mocked(searchLaboratories).mockResolvedValue(response('', [{laboratory: lab('LAB-1', 'Official laboratory name', 'Delhi'), capabilities: [scope]}], 21));
  const localized = [
    ['en', 'Dated BIS LIMS snapshot', 'Next page'],
    ['hi', 'दिनांकित BIS LIMS स्नैपशॉट', 'अगला पृष्ठ'],
    ['mr', 'दिनांकित BIS LIMS स्नॅपशॉट', 'पुढील पान'],
    ['ta', 'தேதியிட்ட BIS LIMS பதிவு', 'அடுத்த பக்கம்'],
    ['bn', 'তারিখযুক্ত BIS LIMS স্ন্যাপশট', 'পরের পৃষ্ঠা'],
  ];
  for (const [language, snapshotText, nextPage] of localized) {
    cleanup(); localStorage.setItem('bis-assistant-language', language);
    render(<LanguageProvider><TestingLabsPage /></LanguageProvider>);
    expect(await screen.findByText(new RegExp(snapshotText))).toBeInTheDocument();
    expect(screen.getByRole('button', { name: nextPage })).toBeInTheDocument();
  }
});
