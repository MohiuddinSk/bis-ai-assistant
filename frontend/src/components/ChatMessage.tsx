import type { ChatResponse } from '../types/chat';
import { CitationCard } from './CitationCard';

const journeyHeadings: Record<string, string> = { direct_answer: 'Applicable standards', explanation: 'Why each standard applies', next_steps: 'Your personalized checklist and next action', important: 'Important conditions or limitations', clarification: 'We need one more detail' };
export function ChatMessage({ role, text, response, onSuggestedReply, busy = false, journey = false, sourceHeading = 'Sources' }: { role: 'user' | 'assistant'; text: string; response?: ChatResponse; onSuggestedReply?: (reply: string) => void; busy?: boolean; journey?: boolean; sourceHeading?: string }) {
  const citations = Array.from(
    new Map((response?.citations ?? []).map((citation) => [citation.chunk_id, citation])).values(),
  );
  const sections = response?.answer_sections ?? [];
  return <article className={`message ${role}`}>
    {role === 'assistant' && response && <span className={`answer-status ${response.needs_clarification ? 'clarification-needed' : response.insufficient_evidence ? 'insufficient' : 'grounded'}`}>{response.needs_clarification ? 'Need more details' : response.insufficient_evidence ? 'Evidence insufficient' : 'Grounded answer'}</span>}
    {sections.length > 0 ? <div className={`guided-answer ${journey ? 'journey-guidance' : ''}`}>{sections.map((section, index) => <section key={`${section.type}-${index}`} className={`guided-section ${section.type}`}>{journey && <p className="journey-section-label">{journeyHeadings[section.type] ?? section.title}</p>}<h3>{section.title}</h3>{section.content && <p>{section.content}</p>}{section.items.length > 0 && <ol>{section.items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ol>}</section>)}</div> : <p className="answer-text">{text}</p>}
    {(response?.suggested_replies?.length ?? 0) > 0 && onSuggestedReply && <div className="suggested-replies" role="group" aria-label="Suggested replies">{response!.suggested_replies!.map(reply => <button type="button" key={reply} disabled={busy} onClick={() => onSuggestedReply(reply)}>{reply}</button>)}</div>}
    {citations.length > 0 && <section className="sources" aria-label={`${sourceHeading} (${citations.length})`}><h3>{sourceHeading} <span>{citations.length}</span></h3><div className="citation-list">{citations.map(c => <CitationCard key={`${c.citation_id}-${c.chunk_id}`} citation={c} />)}</div></section>}
  </article>;
}
