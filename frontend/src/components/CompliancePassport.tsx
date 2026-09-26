import type { AnswerSection, ChatResponse, Citation } from '../types/chat';
import type { ComplianceProfile } from '../types/compliance';
import { useLanguage } from '../i18n/LanguageContext';
import { languageNames, profileLabelKeys } from '../i18n/translations';

export type PassportStatus = 'available' | 'needs_information' | 'needs_verification';

function stableHash(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0').toUpperCase();
}

function cited(section: AnswerSection) { return section.citation_ids.length > 0; }

/** Stable evidence references in their first appearance in finalized passport sections. */
export function passportCitations(guidance: ChatResponse): Citation[] {
  const citationsById = new Map(guidance.citations.map((citation) => [citation.citation_id, citation]));
  const seen = new Set<string>();
  const references: Citation[] = [];
  for (const section of guidance.answer_sections ?? []) {
    if (!['direct_answer', 'explanation', 'next_steps', 'important'].includes(section.type)) continue;
    for (const id of section.citation_ids) {
      if (seen.has(id)) continue;
      const citation = citationsById.get(id);
      if (!citation) continue;
      seen.add(id);
      references.push(citation);
    }
  }
  return references;
}

/** A deterministic display identifier, never a certificate or backend record. */
export function compliancePassportId(profile: ComplianceProfile, guidance: ChatResponse): string {
  const canonicalProfile = { role: profile.role, product_description: profile.product_description, power_type: profile.power_type, intended_age_group: profile.intended_age_group, goal: profile.goal, application_stage: profile.application_stage, additional_context: profile.additional_context };
  const evidence = passportCitations(guidance).map(({ citation_id, chunk_id, source_filename, page_start, page_end }) => ({ citation_id, chunk_id, source_filename, page_start, page_end }));
  return `BIS-CP-${stableHash(JSON.stringify({ profile: canonicalProfile, evidence }))}`;
}

export function passportStatus(profile: ComplianceProfile, guidance: ChatResponse): PassportStatus {
  const hasCitedEvidence = passportCitations(guidance).length > 0;
  if (!guidance.grounded || guidance.insufficient_evidence || guidance.needs_clarification || !hasCitedEvidence) return 'needs_verification';
  if (!profile.product_description.trim() || [profile.power_type, profile.intended_age_group, profile.application_stage, profile.goal].includes('not_sure')) return 'needs_information';
  return 'available';
}

function sourceRows(citations: Citation[]) {
  return citations.map((citation) => ({ id: citation.citation_id, filename: citation.source_filename, pages: citation.page_start === citation.page_end ? String(citation.page_start ?? '') : `${citation.page_start ?? ''}–${citation.page_end ?? ''}`, excerpt: citation.excerpt }));
}

function SectionList({ sections }: { sections: AnswerSection[] }) {
  return <>{sections.map((section, index) => <section className="passport-subsection" key={`${section.type}-${section.title}-${index}`}><h3>{section.title}</h3>{section.content && <p>{section.content}</p>}{section.items.length > 0 && <ol>{section.items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ol>}</section>)}</>;
}

export function CompliancePassportContent({ profile, guidance, generatedAt }: { profile: ComplianceProfile; guidance: ChatResponse; generatedAt: Date }) {
  const { language, t } = useLanguage();
  const label = (value: string) => t(profileLabelKeys[value as keyof typeof profileLabelKeys]);
  const sections = guidance.answer_sections ?? [];
  const direct = sections.filter((section) => section.type === 'direct_answer' && cited(section));
  const findings = sections.filter((section) => section.type === 'explanation' && cited(section));
  const limitations = sections.filter((section) => section.type === 'important');
  const actions = sections.flatMap((section) => section.type === 'next_steps' && cited(section) ? section.items : []).slice(0, 3);
  const sources = passportCitations(guidance);
  const status = passportStatus(profile, guidance);
  const missingProfile = [!profile.product_description.trim() ? t('profileProduct') : null, profile.power_type === 'not_sure' ? t('profilePower') : null, profile.intended_age_group === 'not_sure' ? t('profileAge') : null, profile.application_stage === 'not_sure' ? t('profileStage') : null, profile.goal === 'not_sure' ? t('profileGoal') : null].filter((value): value is string => Boolean(value));
  const statusLabel = status === 'available' ? t('passportAvailable') : status === 'needs_information' ? t('passportNeedsInformation') : t('passportNeedsVerification');
  const id = compliancePassportId(profile, guidance);
  return <>
    <header className="passport-heading"><p className="eyebrow">{t('passportTitle')}</p><h2>{t('passportTitle')}</h2><p className={`passport-status ${status}`}>{statusLabel}</p><dl className="passport-metadata"><dt>{t('passportReportId')}</dt><dd>{id}</dd><dt>{t('passportGenerated')}</dt><dd><time dateTime={generatedAt.toISOString()}>{generatedAt.toLocaleString(language)}</time></dd><dt>{t('passportLanguage')}</dt><dd>{languageNames[language]}</dd></dl><p className="passport-notice">{t('passportNotice')}</p></header>
    <section className="passport-section"><h2>{t('passportProductProfile')}</h2><p className="passport-user-provided">{t('passportUserProvided')}</p><dl><dt>{t('profileProduct')}</dt><dd>{profile.product_description}</dd><dt>{t('profilePower')}</dt><dd>{label(profile.power_type)}</dd><dt>{t('profileAge')}</dt><dd>{label(profile.intended_age_group)}</dd><dt>{t('profileStage')}</dt><dd>{label(profile.application_stage)}</dd><dt>{t('profileGoal')}</dt><dd>{label(profile.goal)}</dd></dl></section>
    {direct.length > 0 && <section className="passport-section"><h2>{t('passportApplicable')}</h2><SectionList sections={direct} /></section>}
    {findings.length > 0 && <section className="passport-section"><h2>{t('passportFindings')}</h2><SectionList sections={findings} /></section>}
    <section className="passport-section"><h2>{t('passportMissingProfile')}</h2>{missingProfile.length > 0 ? <ul>{missingProfile.map((field) => <li key={field}>{field}</li>)}</ul> : <p>{t('passportNoMissing')}</p>}</section>
    <section className="passport-section"><h2>{t('passportVerificationNeeded')}</h2>{limitations.length > 0 ? <SectionList sections={limitations} /> : status === 'needs_verification' ? <p>{t('passportEvidenceVerification')}</p> : <p>{t('passportNoVerification')}</p>}</section>
    <section className="passport-section"><h2>{t('passportNextActions')}</h2>{actions.length > 0 ? <ol>{actions.map((action, index) => <li key={index}>{action}</li>)}</ol> : <p>{t('passportNoActions')}</p>}</section>
    <section className="passport-section"><h2>{t('passportSources')}</h2>{sourceRows(sources).map((source) => <article className="passport-source" key={source.id}><p><strong>{source.id}</strong> — <span className="passport-filename">{source.filename}</span> — {t('pages')} {source.pages}</p><p>{source.excerpt}</p></article>)}</section>
  </>;
}

export function CompliancePassport({ profile, guidance, generatedAt }: { profile: ComplianceProfile; guidance: ChatResponse; generatedAt: Date }) {
  const { t } = useLanguage();
  return <section className="compliance-passport" aria-label={t('passportTitle')}><CompliancePassportContent profile={profile} guidance={guidance} generatedAt={generatedAt} /></section>;
}
