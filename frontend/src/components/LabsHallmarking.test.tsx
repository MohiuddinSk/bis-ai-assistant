import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it } from 'vitest';
import { LanguageProvider } from '../i18n/LanguageContext';
import { HallmarkingPage, TestingLabsPage } from './LabsHallmarking';

afterEach(() => { cleanup(); localStorage.clear(); });

it('filters only the dated, BIS-LIMS-sourced local lab observations and hands other searches to LIMS', async () => {
  render(<LanguageProvider><TestingLabsPage /></LanguageProvider>);
  const user = userEvent.setup();
  expect(screen.getByText(/2 records, not a live or complete BIS directory/)).toBeInTheDocument();
  expect(screen.getByText('PRESTO LABORATORIES PRIVATE LIMITED')).toBeInTheDocument();
  expect(screen.getByText('Testtex India Laboratories Private Limited, Noida')).toBeInTheDocument();
  await user.type(screen.getByLabelText('IS number, product, laboratory or location'), 'IS 4151');
  await user.click(screen.getByRole('button', { name: 'Search checked records' }));
  expect(screen.getByText('PRESTO LABORATORIES PRIVATE LIMITED')).toBeInTheDocument();
  expect(screen.queryByText('Testtex India Laboratories Private Limited, Noida')).toBeNull();
  expect(screen.getByText('₹14,000')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Search current IS scope and testing charges in BIS LIMS ↗' })).toHaveAttribute('href', 'https://lims.bis.gov.in/home/search_is_number/?is_number__doc_no=4151');
  await user.clear(screen.getByLabelText('IS number, product, laboratory or location'));
  await user.type(screen.getByLabelText('IS number, product, laboratory or location'), 'Noida');
  await user.click(screen.getByRole('button', { name: 'Search checked records' }));
  expect(screen.getByText('Testtex India Laboratories Private Limited, Noida')).toBeInTheDocument();
  await user.clear(screen.getByLabelText('IS number, product, laboratory or location'));
  await user.type(screen.getByLabelText('IS number, product, laboratory or location'), 'IS 99999');
  await user.click(screen.getByRole('button', { name: 'Search checked records' }));
  expect(screen.getByText(/This does not mean BIS LIMS has no suitable lab/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Search current IS scope and testing charges in BIS LIMS ↗' })).toHaveAttribute('href', 'https://lims.bis.gov.in/home/search_is_number/?is_number__doc_no=99999');
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
  expect(screen.getByRole('link', { name: 'Open official BIS Care app information ↗' })).toHaveAttribute('href', 'https://www.bis.gov.in/bis-apps/?lang=en');
  expect(screen.queryByText(/^HUID verified$/i)).toBeNull();
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
