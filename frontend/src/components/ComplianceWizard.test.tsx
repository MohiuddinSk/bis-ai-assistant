import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { ComplianceWizard } from './ComplianceWizard';

const guidance = { answer: 'IS 15644 is primary.', grounded: true, insufficient_evidence: false, evidence_count: 1, citations: [{ citation_id: 'S1', source_filename: 'manual.pdf', page_start: 4, page_end: 4, chunk_id: 'c1', excerpt: '<b>IS 15644</b>' }], model: 'fake', generation_mode: 'extractive_fallback' as const, disclaimer: 'Verify.', answer_sections: [{ type: 'direct_answer' as const, title: 'Direct answer', content: 'IS 15644 is primary.', items: [], citation_ids: ['S1'] }] };
const response = { profile: { role: 'manufacturer', product_description: 'Toy car', power_type: 'not_sure', intended_age_group: 'not_sure', goal: 'identify_standards', application_stage: 'not_sure', additional_context: null }, guidance };
const ok = (body: unknown) => ({ ok: true, json: async () => body });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

async function reachReview(user = userEvent.setup()) {
  render(<ComplianceWizard />);
  await user.click(screen.getByRole('button', { name: 'Next' }));
  await user.type(screen.getByLabelText('Describe your product'), 'Toy car');
  for (let index = 0; index < 5; index += 1) await user.click(screen.getByRole('button', { name: 'Next' }));
  return user;
}

it('renders all seven accessible steps with progress and back navigation', async () => {
  const user = userEvent.setup(); render(<ComplianceWizard />);
  expect(screen.getByText(/Step 1 of 7/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Next' }));
  expect(screen.getByText(/Step 2 of 7/)).toBeInTheDocument();
  await user.type(screen.getByLabelText('Describe your product'), 'Car');
  await user.click(screen.getByRole('button', { name: 'Previous' }));
  await user.click(screen.getByRole('button', { name: 'Next' }));
  expect(screen.getByLabelText('Describe your product')).toHaveValue('Car');
});

it('blocks blank and one-character product descriptions', async () => {
  const user = userEvent.setup(); render(<ComplianceWizard />); await user.click(screen.getByRole('button', { name: 'Next' }));
  const next = screen.getByRole('button', { name: 'Next' }); expect(next).toBeDisabled();
  await user.type(screen.getByLabelText('Describe your product'), 'x'); expect(next).toBeDisabled();
});

it('offers Not sure across choice steps and shows the complete review', async () => {
  const user = userEvent.setup(); render(<ComplianceWizard />); expect(screen.getByLabelText('Not sure')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Next' })); await user.type(screen.getByLabelText('Describe your product'), 'Toy');
  for (let index = 0; index < 5; index += 1) { await user.click(screen.getByRole('button', { name: 'Next' })); if (index < 4) expect(screen.getByLabelText('Not sure')).toBeInTheDocument(); }
  expect(screen.getByText('Review your answers')).toBeInTheDocument(); expect(screen.getByText('Toy')).toBeInTheDocument();
});

it('offers the complete compliance roadmap goal', async () => {
  const user = userEvent.setup(); render(<ComplianceWizard />);
  await user.click(screen.getByRole('button', { name: 'Next' }));
  await user.type(screen.getByLabelText('Describe your product'), 'Toy');
  await user.click(screen.getByRole('button', { name: 'Next' }));
  await user.click(screen.getByRole('button', { name: 'Next' }));
  await user.click(screen.getByRole('button', { name: 'Next' }));
  expect(screen.getByLabelText('Guide me through the complete process')).toBeInTheDocument();
});

it('posts the exact normalized profile once and renders sections, citations, and PDF link', async () => {
  const fetchMock = vi.fn().mockResolvedValue(ok(response)); vi.stubGlobal('fetch', fetchMock); const user = await reachReview();
  await user.click(screen.getByRole('button', { name: 'Generate guidance' }));
  expect(await screen.findByRole('heading', { name: 'Direct answer' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /manual.pdf.*page 4/i })).toBeInTheDocument();
  const body = JSON.parse(fetchMock.mock.calls[0][1].body); expect(body).toEqual(response.profile); expect(fetchMock).toHaveBeenCalledTimes(1);
});

it('shows loading, prevents duplicates, and retries a failure', async () => {
  let resolve!: (value: unknown) => void; const pending = new Promise(value => { resolve = value; }); const fetchMock = vi.fn().mockReturnValueOnce(pending); vi.stubGlobal('fetch', fetchMock); const user = await reachReview();
  await user.click(screen.getByRole('button', { name: 'Generate guidance' })); expect(screen.getByRole('button', { name: /Generating/ })).toBeDisabled(); expect(fetchMock).toHaveBeenCalledTimes(1);
  await act(async () => resolve({ ok: false, status: 503, json: async () => ({}) })); await user.click(await screen.findByRole('button', { name: 'Retry' }));
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it('renders insufficient and raw HTML as harmless text, then starts over', async () => {
  const unsafe = { ...response, guidance: { ...guidance, answer: '<b>insufficient</b>', grounded: false, insufficient_evidence: true, citations: [], answer_sections: [] } };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(unsafe))); const user = await reachReview(); await user.click(screen.getByRole('button', { name: 'Generate guidance' }));
  expect(await screen.findByText('<b>insufficient</b>')).toBeInTheDocument(); expect(document.querySelector('b')).toBeNull(); await user.click(screen.getByRole('button', { name: 'Start over' })); expect(screen.getByText(/Step 1 of 7/)).toBeInTheDocument();
});

it('renders a wizard clarification as Need more details', async () => {
  const question = 'Is the toy battery-operated, mains-powered, or non-electric?';
  const clarification = {
    ...response,
    guidance: {
      ...guidance,
      answer: question,
      grounded: false,
      insufficient_evidence: false,
      needs_clarification: true,
      generation_mode: 'clarification' as const,
      citations: [],
      answer_sections: [{
        type: 'clarification' as const,
        title: 'Need more details',
        content: question,
        items: [],
        citation_ids: [],
      }],
    },
  };
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(clarification)));
  const user = await reachReview();
  await user.click(screen.getByRole('button', { name: 'Generate guidance' }));

  expect(await screen.findByText('Need more details', { selector: '.answer-status' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Need more details' })).toBeInTheDocument();
  expect(screen.getByText(question)).toBeInTheDocument();
  expect(screen.queryByText('Evidence insufficient')).not.toBeInTheDocument();
});

it('aborts the active request on unmount', async () => {
  let captured: AbortSignal | undefined; vi.stubGlobal('fetch', vi.fn((_url, init) => { captured = init?.signal; return new Promise(() => undefined); })); const user = await reachReview(); await user.click(screen.getByRole('button', { name: 'Generate guidance' })); cleanup(); await waitFor(() => expect(captured?.aborted).toBe(true));
});
