import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { ComplianceWizard } from './ComplianceWizard';

const guidance = { answer: 'Grounded answer.', grounded: true, insufficient_evidence: false, evidence_count: 1, citations: [{ citation_id: 'S1', source_filename: 'manual.pdf', page_start: 4, page_end: 4, chunk_id: 'c1', excerpt: 'IS 15644 applies.' }], model: 'fake', generation_mode: 'extractive_fallback' as const, disclaimer: 'Verify.', answer_sections: [
  { type: 'direct_answer' as const, title: 'Standards found', content: 'IS 15644 applies.', items: [], citation_ids: ['S1'] },
  { type: 'explanation' as const, title: 'Reason', content: 'The evidence covers this product.', items: [], citation_ids: ['S1'] },
  { type: 'next_steps' as const, title: 'Next steps', content: null, items: ['Review the cited source.'], citation_ids: ['S1'] },
  { type: 'important' as const, title: 'Important condition', content: 'Verify before relying on guidance.', items: [], citation_ids: ['S1'] },
] };
const profile = { role: 'manufacturer', product_description: 'Toy car', power_type: 'battery_operated', intended_age_group: '3_to_8', goal: 'identify_standards', application_stage: 'researching', additional_context: null };
const response = { profile, guidance };
const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

async function reachFinal(user = userEvent.setup(), role: 'Consumer' | 'Manufacturer' = 'Manufacturer', powerLabel?: string) {
  render(<ComplianceWizard />); await user.click(screen.getByRole('button', { name: role }));
  await user.type(screen.getByLabelText('Product description or type'), 'Toy car');
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  if (powerLabel) await user.click(screen.getByLabelText(powerLabel));
  for (let index = 0; index < 3; index += 1) await user.click(screen.getByRole('button', { name: 'Continue' }));
  return user;
}

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
  expect(await screen.findByText('IS 15644 applies.')).toBeInTheDocument(); expect(screen.queryByText(untrustedText)).not.toBeInTheDocument(); expect(screen.getByRole('link', { name: /manual.pdf.*page 4/i })).toBeInTheDocument();
});

it('renders grounded standards, explanation, checklist, conditions, and verified sources', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok(response))); const user = await reachFinal(); await user.click(screen.getByRole('button', { name: 'Generate my guidance' }));
  for (const heading of ['Applicable standards', 'Why each standard applies', 'Your personalized checklist and next action', 'Important conditions or limitations']) expect(await screen.findByText(heading)).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: /Verified sources/i })).toBeInTheDocument(); expect(screen.getByRole('link', { name: /manual.pdf.*page 4/i })).toBeInTheDocument();
});

it('renders battery, mains-powered and non-electric guidance through the same grounded result path', async () => {
  for (const power_type of ['battery_operated', 'mains_electric', 'non_electric']) {
    cleanup(); vi.restoreAllMocks(); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ok({ ...response, profile: { ...profile, power_type } }))); const user = await reachFinal(userEvent.setup(), 'Manufacturer', power_type === 'battery_operated' ? undefined : power_type === 'mains_electric' ? 'Mains-powered' : 'Non-electric');
    await user.click(screen.getByRole('button', { name: 'Generate my guidance' })); expect(await screen.findByText('Applicable standards')).toBeInTheDocument();
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
  expect(await screen.findByRole('heading', { name: 'We need one more detail' })).toBeInTheDocument(); expect(screen.queryByText('Your personalized checklist and next action')).not.toBeInTheDocument(); await user.click(screen.getByRole('button', { name: 'Edit this answer' })); expect(screen.getByText('Step 2 of 5')).toBeInTheDocument();
});

it('is keyboard-accessible and aborts an active request on unmount', async () => {
  const user = userEvent.setup(); render(<ComplianceWizard />); await user.keyboard('{Tab}{Enter}'); expect(screen.getByText(/consumer journey/i)).toBeInTheDocument(); cleanup();
  let captured: AbortSignal | undefined; vi.stubGlobal('fetch', vi.fn((_url, init) => { captured = init?.signal; return new Promise(() => undefined); })); const manufacturer = await reachFinal(); await manufacturer.click(screen.getByRole('button', { name: 'Generate my guidance' })); cleanup(); await waitFor(() => expect(captured?.aborted).toBe(true));
});
