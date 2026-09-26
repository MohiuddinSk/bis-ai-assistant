import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { getComplianceGuide } from '../services/api';
import type { ComplianceGuideResponse, ComplianceProfile, Role } from '../types/compliance';
import { useLanguage } from '../i18n/LanguageContext';
import { profileLabelKeys } from '../i18n/translations';
import type { Language, TranslationKey } from '../i18n/translations';
import { ChatMessage } from './ChatMessage';
import { CompliancePrintReport } from './CompliancePrintReport';
import { CompliancePassport } from './CompliancePassport';
import { printComplianceReport } from './printComplianceReport';

const stepKeys: TranslationKey[] = ['stepProduct', 'stepPower', 'stepAge', 'stepStage', 'stepNeed'];
const helpKeys: TranslationKey[] = ['helpProduct', 'helpPower', 'helpAge', 'helpStage', 'helpNeed'];
const editStep = { product_description: 0, power_type: 1, age_group: 2, application_stage: 3, goal: 4 } as const;
export const initialProfile: ComplianceProfile = { role: 'manufacturer', product_description: '', power_type: 'not_sure', intended_age_group: 'not_sure', goal: 'identify_standards', application_stage: 'not_sure', additional_context: null };
const choices = { power_type: ['battery_operated', 'mains_electric', 'non_electric', 'not_sure'], intended_age_group: ['under_3', '3_to_8', 'over_8', 'multiple', 'not_sure'], application_stage: ['researching', 'preparing_application', 'existing_licence', 'scope_extension', 'not_sure'], goal: ['identify_standards', 'new_licence', 'add_new_series', 'check_exemption', 'understand_transition', 'complete_roadmap', 'not_sure'] } as const;
const reviewFields = [['product_description', 'profileProduct', 'editProduct'], ['power_type', 'profilePower', 'editPower'], ['age_group', 'profileAge', 'editAge'], ['application_stage', 'profileStage', 'editStage'], ['goal', 'profileGoal', 'editGoal']] as const;

export function ComplianceWizard() {
  const { t, language } = useLanguage();
  const [role, setRole] = useState<Role | null>(null); const [step, setStep] = useState(0); const [profile, setProfile] = useState<ComplianceProfile>(initialProfile); const [result, setResult] = useState<ComplianceGuideResponse | null>(null); const [reportGeneratedAt, setReportGeneratedAt] = useState<Date | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [touched, setTouched] = useState(false); const [updatingResult, setUpdatingResult] = useState(false); const controller = useRef<AbortController | null>(null); const localizationController = useRef<AbortController | null>(null); const localizationVersion = useRef(0); const resultVariants = useRef(new Map<Language, ComplianceGuideResponse>()); const submittedProfile = useRef<ComplianceProfile | null>(null); const printReportRef = useRef<HTMLElement | null>(null);
  useEffect(() => () => { controller.current?.abort(); localizationController.current?.abort(); }, []);
  useEffect(() => {
    if (!result) return;
    localizationController.current?.abort();
    const cached = resultVariants.current.get(language);
    if (cached) {
      if (cached !== result) setResult(cached);
      setUpdatingResult(false);
      return;
    }
    const nextController = new AbortController();
    localizationController.current = nextController;
    const version = ++localizationVersion.current;
    setUpdatingResult(true);
    void getComplianceGuide({ ...(submittedProfile.current ?? result.profile), response_language: language }, nextController.signal)
      .then((localizedResult) => {
        if (nextController.signal.aborted || localizationVersion.current !== version) return;
        resultVariants.current.set(language, localizedResult);
        setResult(localizedResult);
      })
      .catch(() => {
        // Keep the last successful guidance. Backend error bodies are not displayed.
      })
      .finally(() => {
        if (!nextController.signal.aborted && localizationVersion.current === version) setUpdatingResult(false);
      });
    return () => nextController.abort();
  }, [language, result]);
  const label = (value: string) => t(profileLabelKeys[value as keyof typeof profileLabelKeys]);
  const descriptionValid = profile.product_description.trim().length >= 2 && profile.product_description.trim().length <= 300;
  const chooseRole = (next: Role) => { setRole(next); setProfile(current => ({ ...current, role: next })); setStep(0); setError(''); };
  const setChoice = (field: keyof typeof choices, value: string) => setProfile(current => ({ ...current, [field]: value }));
  const reset = () => { controller.current?.abort(); localizationController.current?.abort(); localizationVersion.current += 1; resultVariants.current.clear(); submittedProfile.current = null; setRole(null); setProfile(initialProfile); setStep(0); setResult(null); setReportGeneratedAt(null); setError(''); setBusy(false); setTouched(false); setUpdatingResult(false); };
  const generate = async () => { if (busy || !descriptionValid || !role) return; controller.current?.abort(); localizationController.current?.abort(); localizationVersion.current += 1; resultVariants.current.clear(); const requestProfile = { ...profile, role, product_description: profile.product_description.trim() }; submittedProfile.current = requestProfile; const nextController = new AbortController(); controller.current = nextController; setBusy(true); setError(''); try { const nextResult = await getComplianceGuide({ ...requestProfile, response_language: language }, nextController.signal); resultVariants.current.set(language, nextResult); setResult(nextResult); setReportGeneratedAt(new Date()); } catch (reason) { if (!nextController.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to generate guidance.'); } finally { if (!nextController.signal.aborted) setBusy(false); } };
  const edit = (field: keyof typeof editStep) => { localizationController.current?.abort(); localizationVersion.current += 1; setUpdatingResult(false); setResult(null); setStep(editStep[field]); setError(''); };
  const choiceStep = (field: keyof typeof choices) => <fieldset><legend>{t(stepKeys[step])}</legend><p className="wizard-help">{t(helpKeys[step])}</p>{choices[field].map(value => <label className="wizard-choice" key={value}><input type="radio" name={field} checked={profile[field] === value} onChange={() => setChoice(field, value)} />{label(value)}</label>)}</fieldset>;
  const clarificationField = result?.guidance.assistant_context?.expected_slots?.[0]; const clarificationCanEdit = clarificationField && clarificationField in editStep;
  const progress = t('stepProgress').replace('{current}', String(step + 1));

  if (!role) return <section className="wizard journey-entry" aria-label={t('wizardEyebrow')}><p className="eyebrow">{t('wizardEyebrow')}</p><h2>{t('wizardEntryTitle')}</h2><p className="journey-title">{t('wizardEntryLead')}</p><p>{t('wizardEntryDescription')}</p><div className="journey-cards"><button type="button" className="journey-card consumer-card" aria-label={t('roleConsumer')} onClick={() => chooseRole('consumer')}><span>{t('roleConsumer')}</span><strong>{t('consumerCard')}</strong></button><button type="button" className="journey-card manufacturer-card" aria-label={t('roleManufacturer')} onClick={() => chooseRole('manufacturer')}><span>{t('roleManufacturer')}</span><strong>{t('manufacturerCard')}</strong><em>{t('recommendedJourney')}</em></button></div></section>;
  if (result && result.guidance.needs_clarification) return <section className="wizard journey-result clarification-result" aria-label={t('clarificationTitle')}><p className="eyebrow">{t('clarificationEyebrow')}</p><h2>{t('clarificationTitle')}</h2><p>{t('clarificationDescription')}</p>{updatingResult && <p className="answer-update" aria-live="polite">{t('updatingAnswers')}</p>}<ChatMessage role="assistant" text={result.guidance.answer} response={result.guidance} />{clarificationCanEdit && <button type="button" onClick={() => edit(clarificationField as keyof typeof editStep)}>{t('editThisAnswer')}</button>}<button type="button" className="secondary" onClick={reset}>{t('startOver')}</button></section>;
  if (result) { const passportProfile = submittedProfile.current ?? result.profile; const canPassport = Boolean(result.guidance.grounded && !result.guidance.insufficient_evidence && !result.guidance.needs_clarification && !error && !busy && reportGeneratedAt); return <>{canPassport && createPortal(<CompliancePrintReport ref={printReportRef} profile={passportProfile} guidance={result.guidance} generatedAt={reportGeneratedAt!} />, document.body)}<section className="wizard journey-result" aria-label={t('journeyResultAria')}><div className="result-heading"><div><p className="eyebrow">{t('groundedGuidance')}</p><h2>{t('journeyTitle')}</h2><p>{t('journeyDescription')}</p></div><div className="result-actions">{canPassport && <button type="button" onClick={event => { if (printReportRef.current) printComplianceReport(printReportRef.current, event.currentTarget, t('printReportTitle')); }} aria-label={t('saveAsPdfAria')}>{t('saveAsPdf')}</button>}<button type="button" className="secondary" onClick={reset}>{t('startOver')}</button></div></div>{updatingResult && <p className="answer-update" aria-live="polite">{t('updatingAnswers')}</p>}<section className="journey-category journey-profile-summary" aria-labelledby="journey-product-profile"><h2 id="journey-product-profile">{t('profileTitle')}</h2><dl><dt>{t('profileProduct')}</dt><dd>{passportProfile.product_description}</dd><dt>{t('profilePower')}</dt><dd>{label(passportProfile.power_type)}</dd><dt>{t('profileAge')}</dt><dd>{label(passportProfile.intended_age_group)}</dd><dt>{t('profileStage')}</dt><dd>{label(passportProfile.application_stage)}</dd><dt>{t('profileGoal')}</dt><dd>{label(passportProfile.goal)}</dd></dl><p>{t('profileNote')}</p></section><ChatMessage role="assistant" text={result.guidance.answer} response={result.guidance} presentation="compliance-journey" />{canPassport && <CompliancePassport profile={passportProfile} guidance={result.guidance} generatedAt={reportGeneratedAt!} />}{error && <p role="alert" className="error">{error} <button type="button" onClick={() => void generate()}>{t('retry')}</button></p>}<p className="report-disclaimer">{t('reportDisclaimer')}</p><p className="wizard-disclaimer">{result.guidance.disclaimer}</p></section></>; }

  return <section className="wizard journey-form" aria-label={`${label(role)} ${t('journeyTitle')}`}><div className="journey-form-heading"><div><p className="eyebrow">{label(role)} {t('journeyLabel')}</p><h2>{t(stepKeys[step])}</h2></div><button type="button" className="secondary" onClick={reset} disabled={busy}>{t('startOver')}</button></div><p aria-live="polite" className="progress-label">{progress}</p><progress aria-label={progress} value={step + 1} max={5} />{step === 0 && <div><label htmlFor="wizard-product">{t('productDescription')}</label><p className="wizard-help">{t('helpProduct')}</p><textarea id="wizard-product" aria-describedby="wizard-product-error" maxLength={300} value={profile.product_description} onBlur={() => setTouched(true)} onChange={event => setProfile(current => ({ ...current, product_description: event.target.value }))} />{touched && !descriptionValid && <p id="wizard-product-error" role="alert">{t('validationProduct')}</p>}</div>}{step === 1 && choiceStep('power_type')}{step === 2 && choiceStep('intended_age_group')}{step === 3 && choiceStep('application_stage')}{step === 4 && choiceStep('goal')}{step === 4 && <section className="wizard-review" aria-label={t('reviewAnswers')}><h3>{t('reviewAnswers')}</h3><dl>{reviewFields.map(([field, titleKey, editKey]) => { const value = field === 'product_description' ? profile.product_description : field === 'age_group' ? label(profile.intended_age_group) : label(profile[field]); return <div key={field}><dt>{t(titleKey)}</dt><dd>{value || t('notAnswered')}</dd><button type="button" className="text-button" onClick={() => setStep(editStep[field])} disabled={busy}>{t(editKey)}</button></div>; })}</dl></section>}<div className="wizard-actions"><button type="button" onClick={() => setStep(current => current - 1)} disabled={step === 0 || busy}>{t('back')}</button>{step < 4 ? <button type="button" onClick={() => { if (step === 0) setTouched(true); if (step !== 0 || descriptionValid) setStep(current => current + 1); }} disabled={busy || (step === 0 && !descriptionValid)}>{t('continue')}</button> : <button type="button" onClick={() => void generate()} disabled={busy || !descriptionValid}>{busy ? t('preparing') : t('generate')}</button>}</div>{error && <p role="alert" className="error">{error} <button type="button" onClick={() => void generate()}>{t('retry')}</button></p>}</section>;
}
