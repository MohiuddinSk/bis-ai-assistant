import type { AnswerSection, ChatResponse, Citation } from '../types/chat';
import { CitationCard } from './CitationCard';
import type { SuggestedAction } from '../suggestedActions';
import { useLanguage } from '../i18n/LanguageContext';
import { journeyCategoryFor, journeyCategoryHeadingKey, sectionHeadingKey, type JourneyCategory } from '../i18n/answerSectionLabels';

type Presentation = 'chat' | 'compliance-journey';

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

function BackendSection({ section }: { section: AnswerSection }) {
  const { t } = useLanguage();
  return <section className={`journey-backend-section ${section.type}`}>
    <h3>{t(sectionHeadingKey(section))}</h3>
    {section.content && <p>{section.content}</p>}
    {section.items.length > 0 && <ol>{section.items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ol>}
  </section>;
}

function JourneyGuidance({ sections }: { sections: AnswerSection[] }) {
  const { t } = useLanguage();
  const grouped = new Map<JourneyCategory, AnswerSection[]>();
  const profile = [] as AnswerSection[];
  for (const section of distinctSections(sections)) {
    if (section.type === 'explanation' && profileTitles.has(section.title.trim().toLowerCase())) profile.push(section);
    else {
      const category = journeyCategoryFor(section);
      grouped.set(category, [...(grouped.get(category) ?? []), section]);
    }
  }
  return <div className="journey-guidance">
    {profile.length > 0 && <section className="journey-category journey-profile-details" aria-label="Profile details from guidance">{profile.map((section, index) => <BackendSection key={`${section.type}-${section.title}-${index}`} section={section} />)}</section>}
    {(['standards', 'summary', 'checklist', 'important'] as JourneyCategory[]).map((category) => {
      const categorySections = grouped.get(category) ?? [];
      return categorySections.length > 0 && <section key={category} className={`journey-category journey-${category}`} aria-labelledby={`journey-${category}`}><h2 id={`journey-${category}`}>{t(journeyCategoryHeadingKey(category))}</h2>{categorySections.map((section, index) => <BackendSection key={`${section.type}-${section.title}-${index}`} section={section} />)}</section>;
    })}
  </div>;
}

function JourneySources({ citations }: { citations: Citation[] }) {
  const { t } = useLanguage();
  const byDocument = new Map<string, Citation[]>();
  for (const citation of citations) {
    const document = citation.source_filename ?? t('source');
    byDocument.set(document, [...(byDocument.get(document) ?? []), citation]);
  }
  return <section className="sources journey-sources" aria-label={`${t('verifiedSources')} (${citations.length})`}><h2>{t('verifiedSources')} <span>{citations.length}</span></h2><details open><summary>{t('viewVerifiedDetails')}</summary>{[...byDocument].map(([document, documentCitations], documentIndex) => <section className="journey-source-document" key={document}><h3>{document}</h3><div className="source-page-chips" aria-label={t('referencedPages').replace('{document}', document)}>{documentCitations.map((citation, citationIndex) => <a key={`${citation.citation_id}-${citation.chunk_id}`} href={`#journey-source-${documentIndex}-${citationIndex}`}>{citation.page_start === citation.page_end ? `${t('page')} ${citation.page_start ?? t('pageUnavailable')}` : `${t('pages')} ${citation.page_start ?? '?'}–${citation.page_end ?? '?'}`}</a>)}</div><div className="citation-list">{documentCitations.map((citation, citationIndex) => <div id={`journey-source-${documentIndex}-${citationIndex}`} key={`${citation.citation_id}-${citation.chunk_id}`}><CitationCard citation={citation} /></div>)}</div></section>)}</details></section>;
}

export function ChatMessage({ role, text, response, suggestedActions, onSuggestedAction, busy = false, presentation = 'chat', sourceHeading }: { role: 'user' | 'assistant'; text: string; response?: ChatResponse; suggestedActions?: SuggestedAction[]; onSuggestedAction?: (action: SuggestedAction) => void; busy?: boolean; presentation?: Presentation; sourceHeading?: string }) {
  const { t } = useLanguage();
  const citations = Array.from(new Map((response?.citations ?? []).map((citation) => [citation.chunk_id, citation])).values());
  const sections = response?.answer_sections ?? [];
  const journey = presentation === 'compliance-journey';
  const displayedSourceHeading = sourceHeading ?? t('sourcesHeading');
  return <article className={`message ${role}`}>
    {role === 'assistant' && response && <span className={`answer-status ${response.response_kind === 'conversation' || response.generation_mode === 'conversation' ? 'conversation' : response.response_kind === 'clarification' || response.needs_clarification ? 'clarification-needed' : response.response_kind === 'limitation' || response.insufficient_evidence ? 'insufficient' : 'grounded'}`}>{response.response_kind === 'conversation' || response.generation_mode === 'conversation' ? t('conversationGuide') : response.response_kind === 'clarification' || response.needs_clarification ? t('evidenceNeedDetails') : response.response_kind === 'limitation' || response.insufficient_evidence ? t('evidenceInsufficient') : t('evidenceGrounded')}</span>}
    {sections.length > 0 ? journey ? <JourneyGuidance sections={sections} /> : <div className="guided-answer">{sections.map((section, index) => <section key={`${section.type}-${index}`} className={`guided-section ${section.type}`}><h3>{t(sectionHeadingKey(section))}</h3>{section.content && <p>{section.content}</p>}{section.items.length > 0 && <ol>{section.items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ol>}</section>)}</div> : <p className="answer-text">{text}</p>}
    {(suggestedActions?.length ?? 0) > 0 && onSuggestedAction && <div className="suggested-replies" role="group" aria-label={t('suggestedReplies')}>{suggestedActions!.map(action => <button type="button" key={action.label} disabled={busy} onClick={() => onSuggestedAction(action)}>{action.label}</button>)}</div>}
    {citations.length > 0 && (journey ? <JourneySources citations={citations} /> : <section className="sources" aria-label={`${displayedSourceHeading} (${citations.length})`}><h3>{displayedSourceHeading} <span>{citations.length}</span></h3><div className="citation-list">{citations.map(c => <CitationCard key={`${c.citation_id}-${c.chunk_id}`} citation={c} />)}</div></section>)}
  </article>;
}
