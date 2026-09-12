import { useEffect, useRef, useState } from 'react';
import { askQuestion, getComplianceGuide } from '../services/api';
import { audienceForRole, type ComplianceGuideResponse, type ComplianceProfile } from '../types/compliance';
import { ChatMessage } from './ChatMessage';

const steps = ['Who are you?', 'Describe your product', 'How is the product powered?', 'Intended age group', 'What guidance do you need?', 'Application stage', 'Review and generate guidance'];
export const initialProfile: ComplianceProfile = { role: 'manufacturer', product_description: '', power_type: 'not_sure', intended_age_group: 'not_sure', goal: 'identify_standards', application_stage: 'not_sure', additional_context: null };
const choices = {
  role: ['manufacturer', 'importer', 'artisan', 'consumer', 'not_sure'],
  power_type: ['battery_operated', 'mains_electric', 'non_electric', 'not_sure'],
  intended_age_group: ['under_3', '3_to_8', 'over_8', 'multiple', 'not_sure'],
  goal: ['identify_standards', 'new_licence', 'add_new_series', 'check_exemption', 'understand_transition', 'complete_roadmap', 'not_sure'],
  application_stage: ['researching', 'preparing_application', 'existing_licence', 'scope_extension', 'not_sure'],
} as const;
const labels: Record<string, string> = { manufacturer: 'Manufacturer', importer: 'Importer', artisan: 'Artisan', consumer: 'Consumer', not_sure: 'Not sure', battery_operated: 'Battery-operated', mains_electric: 'Mains electric', non_electric: 'Non-electric', under_3: 'Under 3', '3_to_8': '3 to 8', over_8: 'Over 8', multiple: 'Multiple age groups', identify_standards: 'Identify applicable standards', new_licence: 'Apply for a new licence', add_new_series: 'Add a new toy series', check_exemption: 'Check a possible exemption', understand_transition: 'Understand a transition order', complete_roadmap: 'Guide me through the complete process', researching: 'Researching', preparing_application: 'Preparing an application', existing_licence: 'Existing licence', scope_extension: 'Extending licence scope' };

export function ComplianceWizard() {
  const [step, setStep] = useState(0);
  const [profile, setProfile] = useState<ComplianceProfile>(initialProfile);
  const [result, setResult] = useState<ComplianceGuideResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [touched, setTouched] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  const descriptionValid = profile.product_description.trim().length >= 2 && profile.product_description.trim().length <= 300;
  const setChoice = (field: keyof typeof choices, value: string) => setProfile(current => ({ ...current, [field]: value }));
  const reset = () => { controller.current?.abort(); setProfile(initialProfile); setStep(0); setResult(null); setError(''); setBusy(false); setTouched(false); };
  const generate = async () => {
    if (busy || !descriptionValid) return;
    controller.current?.abort();
    controller.current = new AbortController();
    setBusy(true); setError('');
    try { setResult(await getComplianceGuide({ ...profile, product_description: profile.product_description.trim() }, controller.current.signal)); }
    catch (reason) { if (!controller.current?.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to generate guidance.'); }
    finally { if (!controller.current?.signal.aborted) setBusy(false); }
  };
  const continueGuidance = async (reply: string) => {
    const context = result?.guidance.assistant_context;
    if (busy || !result || !context) return;
    controller.current?.abort(); controller.current = new AbortController();
    setBusy(true); setError('');
    try {
      const guidance = await askQuestion(reply, audienceForRole(profile.role), context, controller.current.signal);
      if (!controller.current.signal.aborted) setResult(current => current ? { ...current, guidance } : current);
    } catch (reason) {
      if (!controller.current?.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to generate guidance.');
    } finally {
      if (!controller.current?.signal.aborted) setBusy(false);
    }
  };
  const choiceStep = (field: keyof typeof choices) => <fieldset><legend>{steps[step]}</legend>{choices[field].map(value => <label className="wizard-choice" key={value}><input type="radio" name={field} checked={profile[field] === value} onChange={() => setChoice(field, value)} />{labels[value]}</label>)}</fieldset>;

  if (result) return <section className="wizard" aria-label="Compliance Wizard result"><button type="button" onClick={reset}>Start over</button><ChatMessage role="assistant" text={result.guidance.answer} response={result.guidance} busy={busy} onSuggestedReply={result.guidance.assistant_context ? (reply) => void continueGuidance(reply) : undefined} />{error && <p role="alert" className="error">{error}</p>}<p className="wizard-disclaimer">{result.guidance.disclaimer}</p></section>;
  return <section className="wizard" aria-label="Compliance Wizard">
    <h2>Compliance Wizard</h2><p aria-live="polite">Step {step + 1} of 7: {steps[step]}</p><progress aria-label={`Step ${step + 1} of 7`} value={step + 1} max={7} />
    {step === 0 && choiceStep('role')}
    {step === 1 && <div><label htmlFor="wizard-product">Describe your product</label><textarea id="wizard-product" aria-describedby="wizard-product-help wizard-product-error" maxLength={300} value={profile.product_description} onBlur={() => setTouched(true)} onChange={event => setProfile(current => ({ ...current, product_description: event.target.value }))} /><small id="wizard-product-help">Use a short description, such as “battery-operated toy car”.</small>{touched && !descriptionValid && <p id="wizard-product-error" role="alert">Enter between 2 and 300 characters.</p>}</div>}
    {step === 2 && choiceStep('power_type')}{step === 3 && choiceStep('intended_age_group')}{step === 4 && choiceStep('goal')}{step === 5 && choiceStep('application_stage')}
    {step === 6 && <div className="wizard-review"><h3>Review your answers</h3><dl><dt>Role</dt><dd>{labels[profile.role]}</dd><dt>Product</dt><dd>{profile.product_description}</dd><dt>Power</dt><dd>{labels[profile.power_type]}</dd><dt>Age group</dt><dd>{labels[profile.intended_age_group]}</dd><dt>Guidance</dt><dd>{labels[profile.goal]}</dd><dt>Application stage</dt><dd>{labels[profile.application_stage]}</dd></dl><label htmlFor="wizard-context">Anything else? (optional)</label><textarea id="wizard-context" maxLength={500} value={profile.additional_context ?? ''} onChange={event => setProfile(current => ({ ...current, additional_context: event.target.value || null }))} /></div>}
    <div className="wizard-actions"><button type="button" onClick={() => setStep(current => current - 1)} disabled={step === 0 || busy}>Previous</button>{step < 6 ? <button type="button" onClick={() => { if (step === 1) setTouched(true); if (step !== 1 || descriptionValid) setStep(current => current + 1); }} disabled={busy || (step === 1 && !descriptionValid)}>Next</button> : <button type="button" onClick={() => void generate()} disabled={busy || !descriptionValid}>{busy ? 'Generating guidance…' : 'Generate guidance'}</button>}<button type="button" className="secondary" onClick={reset} disabled={busy}>Start over</button></div>
    {error && <p role="alert" className="error">{error} <button type="button" onClick={() => void generate()}>Retry</button></p>}
  </section>;
}
