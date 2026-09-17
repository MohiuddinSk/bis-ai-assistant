import type { AnswerSection, ChatResponse, Citation } from '../types/chat';
import { CitationCard } from './CitationCard';
import type { SuggestedAction } from '../suggestedActions';

type Presentation = 'chat' | 'compliance-journey';
type JourneyCategory = 'standards' | 'why' | 'checklist' | 'important' | 'next-action';

const categoryHeadings: Record<JourneyCategory, string> = {
  standards: 'Applicable standards',
  why: 'Why these standards apply',
  checklist: 'Your compliance checklist',
  important: 'Important conditions',
  'next-action': 'Recommended next action',
};
const profileTitles = new Set(['your profile', 'certification position', 'where this fits in your journey']);

function distinctSections(sections: AnswerSection[]) {
  const seen = new Set<string>();
  return sections.filter((section) => {
    const identity = JSON.stringify([section.type, section.title, section.content ?? null, section.items]);
    if (seen.has(identity)) return false;
    seen.add(identity);
    return true;
  });
}

function categoryFor(section: AnswerSection): JourneyCategory {
  if (section.type === 'direct_answer') return 'standards';
  if (section.type === 'important') return 'important';
  if (section.type === 'next_steps' && section.title.trim().toLowerCase() === 'your next action') return 'next-action';
  if (section.type === 'next_steps') return 'checklist';
  return 'why';
}

function BackendSection({ section }: { section: AnswerSection }) {
  return <section className={`journey-backend-section ${section.type}`}>
    <h3>{section.title}</h3>
    {section.content && <p>{section.content}</p>}
    {section.items.length > 0 && <ol>{section.items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ol>}
  </section>;
}

function JourneyGuidance({ sections }: { sections: AnswerSection[] }) {
  const grouped = new Map<JourneyCategory, AnswerSection[]>();
  const profile = [] as AnswerSection[];
  for (const section of distinctSections(sections)) {
    if (section.type === 'explanation' && profileTitles.has(section.title.trim().toLowerCase())) profile.push(section);
    else {
      const category = categoryFor(section);
      grouped.set(category, [...(grouped.get(category) ?? []), section]);
    }
  }
  return <div className="journey-guidance">
    {profile.length > 0 && <section className="journey-category journey-profile-details" aria-label="Profile details from guidance">{profile.map((section, index) => <BackendSection key={`${section.type}-${section.title}-${index}`} section={section} />)}</section>}
    {(['standards', 'why', 'checklist', 'important', 'next-action'] as JourneyCategory[]).map((category) => {
      const categorySections = grouped.get(category) ?? [];
      return categorySections.length > 0 && <section key={category} className={`journey-category journey-${category}`} aria-labelledby={`journey-${category}`}><h2 id={`journey-${category}`}>{categoryHeadings[category]}</h2>{categorySections.map((section, index) => <BackendSection key={`${section.type}-${section.title}-${index}`} section={section} />)}</section>;
    })}
  </div>;
}

function JourneySources({ citations }: { citations: Citation[] }) {
  const byDocument = new Map<string, Citation[]>();
  for (const citation of citations) {
    const document = citation.source_filename ?? 'Indexed document';
    byDocument.set(document, [...(byDocument.get(document) ?? []), citation]);
  }
  return <section className="sources journey-sources" aria-label={`Verified sources (${citations.length})`}><h2>Verified sources <span>{citations.length}</span></h2><details open><summary>View verified source details</summary>{[...byDocument].map(([document, documentCitations], documentIndex) => <section className="journey-source-document" key={document}><h3>{document}</h3><div className="source-page-chips" aria-label={`Referenced pages in ${document}`}>{documentCitations.map((citation, citationIndex) => <a key={`${citation.citation_id}-${citation.chunk_id}`} href={`#journey-source-${documentIndex}-${citationIndex}`}>{citation.page_start === citation.page_end ? `Page ${citation.page_start ?? 'not available'}` : `Pages ${citation.page_start ?? '?'}–${citation.page_end ?? '?'}`}</a>)}</div><div className="citation-list">{documentCitations.map((citation, citationIndex) => <div id={`journey-source-${documentIndex}-${citationIndex}`} key={`${citation.citation_id}-${citation.chunk_id}`}><CitationCard citation={citation} /></div>)}</div></section>)}</details></section>;
}

export function ChatMessage({ role, text, response, suggestedActions, onSuggestedAction, busy = false, presentation = 'chat', sourceHeading = 'Sources' }: { role: 'user' | 'assistant'; text: string; response?: ChatResponse; suggestedActions?: SuggestedAction[]; onSuggestedAction?: (action: SuggestedAction) => void; busy?: boolean; presentation?: Presentation; sourceHeading?: string }) {
  const citations = Array.from(new Map((response?.citations ?? []).map((citation) => [citation.chunk_id, citation])).values());
  const sections = response?.answer_sections ?? [];
  const journey = presentation === 'compliance-journey';
  return <article className={`message ${role}`}>
    {role === 'assistant' && response && <span className={`answer-status ${response.needs_clarification ? 'clarification-needed' : response.insufficient_evidence ? 'insufficient' : 'grounded'}`}>{response.needs_clarification ? 'Need more details' : response.insufficient_evidence ? 'Evidence insufficient' : 'Grounded answer'}</span>}
    {sections.length > 0 ? journey ? <JourneyGuidance sections={sections} /> : <div className="guided-answer">{sections.map((section, index) => <section key={`${section.type}-${index}`} className={`guided-section ${section.type}`}><h3>{section.title}</h3>{section.content && <p>{section.content}</p>}{section.items.length > 0 && <ol>{section.items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ol>}</section>)}</div> : <p className="answer-text">{text}</p>}
    {(suggestedActions?.length ?? 0) > 0 && onSuggestedAction && <div className="suggested-replies" role="group" aria-label="Suggested replies">{suggestedActions!.map(action => <button type="button" key={action.label} disabled={busy} onClick={() => onSuggestedAction(action)}>{action.label}</button>)}</div>}
    {citations.length > 0 && (journey ? <JourneySources citations={citations} /> : <section className="sources" aria-label={`${sourceHeading} (${citations.length})`}><h3>{sourceHeading} <span>{citations.length}</span></h3><div className="citation-list">{citations.map(c => <CitationCard key={`${c.citation_id}-${c.chunk_id}`} citation={c} />)}</div></section>)}
  </article>;
}
