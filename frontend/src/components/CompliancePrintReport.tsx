import type { AnswerSection, ChatResponse, Citation } from '../types/chat';
import type { ComplianceProfile } from '../types/compliance';

const labels: Record<string, string> = {
  battery_operated: 'Battery-operated', mains_electric: 'Mains-powered', non_electric: 'Non-electric', not_sure: 'Not sure',
  under_3: 'Under 3', '3_to_8': '3 to 8', over_8: 'Over 8', multiple: 'More than one age group',
  researching: 'Researching', preparing_application: 'Preparing an application', existing_licence: 'Already licensed', scope_extension: 'Adding to an existing licence',
  identify_standards: 'Identify applicable standards', new_licence: 'Apply for a new licence', add_new_series: 'Add a new toy series', check_exemption: 'Check a possible exemption', understand_transition: 'Understand a transition order', complete_roadmap: 'Build my compliance roadmap',
};
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
function sourceRows(citations: Citation[]): SourceRow[] {
  const sources = new Map<string, SourceRow>();
  for (const citation of citations) {
    const document = citation.source_filename?.trim() || 'Indexed document';
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

export function CompliancePrintReport({ profile, guidance, generatedAt }: { profile: ComplianceProfile; guidance: ChatResponse; generatedAt: Date }) {
  const sections = distinctSections(guidance.answer_sections ?? []);
  const standards = sections.filter((section) => section.type === 'direct_answer');
  const why = sections.filter((section) => section.type === 'explanation' && !profileOnlyTitles.has(section.title.trim().toLowerCase()));
  const checklist = sections.filter((section) => section.type === 'next_steps' && section.title.trim().toLowerCase() !== 'your next action');
  const nextAction = sections.filter((section) => section.type === 'next_steps' && section.title.trim().toLowerCase() === 'your next action');
  const important = sections.filter((section) => section.type === 'important');
  const sources = sourceRows(guidance.citations);
  return <article className="compliance-print-report print-only" aria-label="Compliance Action Report">
    <header className="print-report-title"><p>BIS Saarthi</p><h1>Compliance Action Report</h1><p>Evidence-grounded informational guidance</p><time dateTime={generatedAt.toISOString()}>Generated {generatedAt.toLocaleString()}</time></header>
    <section className="print-report-section"><h2>Product profile</h2><table><thead><tr><th scope="col">Detail</th><th scope="col">Provided information</th></tr></thead><tbody><tr><th scope="row">Product</th><td>{profile.product_description}</td></tr><tr><th scope="row">Power type</th><td>{labels[profile.power_type]}</td></tr><tr><th scope="row">Intended age group</th><td>{labels[profile.intended_age_group]}</td></tr><tr><th scope="row">Current stage</th><td>{labels[profile.application_stage]}</td></tr><tr><th scope="row">Guidance goal</th><td>{labels[profile.goal]}</td></tr></tbody></table><p className="print-profile-note">These details were provided by the user to personalize the guidance. They are not verified BIS evidence.</p></section>
    {standards.length > 0 && <section className="print-report-section"><h2>Applicable standards</h2><SectionContent sections={standards} /></section>}
    {why.length > 0 && <section className="print-report-section"><h2>Why this applies</h2><SectionContent sections={why} /></section>}
    {checklist.length > 0 && <section className="print-report-section"><h2>Compliance checklist</h2><SectionContent sections={checklist} /></section>}
    {nextAction.length > 0 && <section className="print-report-section print-next-action"><h2>Recommended next action</h2><SectionContent sections={nextAction} /></section>}
    {important.length > 0 && <section className="print-report-section print-important"><h2>Important conditions and limitations</h2><SectionContent sections={important} /></section>}
    {sources.length > 0 && <section className="print-report-section print-sources"><h2>Verified sources</h2><table><thead><tr><th scope="col">Document</th><th scope="col">Referenced pages</th></tr></thead><tbody>{sources.map((source) => <tr key={source.document}><td>{source.document}</td><td>{source.pages.map((page) => page ?? 'Not available').join(', ')}</td></tr>)}</tbody></table></section>}
    <p className="print-report-disclaimer">This is informational guidance, not a BIS licence, certificate, legal opinion, or complete official application package.</p>
    <footer>Verify applicable requirements with BIS or a qualified professional.</footer>
  </article>;
}
