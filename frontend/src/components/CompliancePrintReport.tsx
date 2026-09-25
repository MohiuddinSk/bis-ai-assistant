import { forwardRef } from 'react';
import type { AnswerSection, ChatResponse, Citation } from '../types/chat';
import type { ComplianceProfile } from '../types/compliance';
import { useLanguage } from '../i18n/LanguageContext';
import { profileLabelKeys } from '../i18n/translations';
const profileOnlyTitles = new Set(['your profile', 'certification position', 'where this fits in your journey']);

function distinctSections(sections: AnswerSection[]) {
  const seen = new Set<string>();
  return sections.filter((section) => {
    const identity = JSON.stringify([section.type, section.title, section.content ?? null, section.items]);
    if (seen.has(identity)) return false;
    seen.add(identity);
    return true;
  });
}

function SectionContent({ sections }: { sections: AnswerSection[] }) {
  return <>{sections.map((section, index) => <section className="print-report-subsection" key={`${section.type}-${section.title}-${index}`}>
    <h3>{section.title}</h3>{section.content && <p>{section.content}</p>}
    {section.items.length > 0 && <ol>{section.items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ol>}
  </section>)}</>;
}

type SourceRow = { document: string; pages: Array<number | null> };
function sourceRows(citations: Citation[], fallbackDocument: string): SourceRow[] {
  const sources = new Map<string, SourceRow>();
  for (const citation of citations) {
    const document = citation.source_filename?.trim() || fallbackDocument;
    const key = document.toLocaleLowerCase();
    const row = sources.get(key) ?? { document, pages: [] };
    const start = citation.page_start;
    const end = citation.page_end;
    if (typeof start === 'number' && typeof end === 'number' && end >= start && end - start <= 100) {
      for (let page = start; page <= end; page += 1) row.pages.push(page);
    } else row.pages.push(start ?? end ?? null);
    sources.set(key, row);
  }
  return [...sources.values()].map((row) => ({ ...row, pages: Array.from(new Set(row.pages)).sort((left, right) => (left ?? Infinity) - (right ?? Infinity)) }));
}

export const CompliancePrintReport = forwardRef<HTMLElement, { profile: ComplianceProfile; guidance: ChatResponse; generatedAt: Date }>(function CompliancePrintReport({ profile, guidance, generatedAt }, ref) {
  const { language, t } = useLanguage();
  const label = (value: string) => t(profileLabelKeys[value as keyof typeof profileLabelKeys]);
  const sections = distinctSections(guidance.answer_sections ?? []);
  const standards = sections.filter((section) => section.type === 'direct_answer');
  const why = sections.filter((section) => section.type === 'explanation' && !profileOnlyTitles.has(section.title.trim().toLowerCase()));
  const checklist = sections.filter((section) => section.type === 'next_steps' && section.title.trim().toLowerCase() !== 'your next action');
  const nextAction = sections.filter((section) => section.type === 'next_steps' && section.title.trim().toLowerCase() === 'your next action');
  const important = sections.filter((section) => section.type === 'important');
  const sources = sourceRows(guidance.citations, t('source'));
  return <article ref={ref} className="compliance-print-report print-only" aria-label={t('printReportAria')}>
    <header className="print-report-title"><p>BIS Saarthi</p><h1>{t('printReportTitle')}</h1><p>{t('printReportSubtitle')}</p><time dateTime={generatedAt.toISOString()}>{t('generated')} {generatedAt.toLocaleString(language)}</time></header>
    <section className="print-report-section"><h2>{t('printProductProfile')}</h2><table><thead><tr><th scope="col">{t('printDetail')}</th><th scope="col">{t('printProvidedInformation')}</th></tr></thead><tbody><tr><th scope="row">{t('profileProduct')}</th><td>{profile.product_description}</td></tr><tr><th scope="row">{t('profilePower')}</th><td>{label(profile.power_type)}</td></tr><tr><th scope="row">{t('profileAge')}</th><td>{label(profile.intended_age_group)}</td></tr><tr><th scope="row">{t('profileStage')}</th><td>{label(profile.application_stage)}</td></tr><tr><th scope="row">{t('profileGoal')}</th><td>{label(profile.goal)}</td></tr></tbody></table><p className="print-profile-note">{t('printProfileNote')}</p></section>
    {standards.length > 0 && <section className="print-report-section"><h2>{t('journeyApplicable')}</h2><SectionContent sections={standards} /></section>}
    {why.length > 0 && <section className="print-report-section"><h2>{t('printWhy')}</h2><SectionContent sections={why} /></section>}
    {checklist.length > 0 && <section className="print-report-section"><h2>{t('printChecklist')}</h2><SectionContent sections={checklist} /></section>}
    {nextAction.length > 0 && <section className="print-report-section print-next-action"><h2>{t('journeyNextAction')}</h2><SectionContent sections={nextAction} /></section>}
    {important.length > 0 && <section className="print-report-section print-important"><h2>{t('printImportant')}</h2><SectionContent sections={important} /></section>}
    {sources.length > 0 && <section className="print-report-section print-sources"><h2>{t('verifiedSources')}</h2><table><thead><tr><th scope="col">{t('printDocument')}</th><th scope="col">{t('printReferencedPages')}</th></tr></thead><tbody>{sources.map((source) => <tr key={source.document}><td>{source.document}</td><td>{source.pages.map((page) => page ?? t('pageUnavailable')).join(', ')}</td></tr>)}</tbody></table></section>}
    <p className="print-report-disclaimer">{t('reportDisclaimer')}</p>
    <footer>{t('printFooter')}</footer>
  </article>;
});
