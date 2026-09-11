import type { ChatResponse } from '../types/chat';
import { CitationCard } from './CitationCard';

export function ChatMessage({ role, text, response }: { role: 'user' | 'assistant'; text: string; response?: ChatResponse }) {
  const citations = Array.from(
    new Map((response?.citations ?? []).map((citation) => [citation.chunk_id, citation])).values(),
  );
  return <article className={`message ${role}`}>
    {role === 'assistant' && response && <span className={`answer-status ${response.insufficient_evidence ? 'insufficient' : 'grounded'}`}>{response.insufficient_evidence ? 'Evidence insufficient' : 'Grounded answer'}</span>}
    <p className="answer-text">{text}</p>
    {citations.length > 0 && <section className="sources" aria-label={`Sources (${citations.length})`}><h3>Sources <span>{citations.length}</span></h3><div className="citation-list">{citations.map(c => <CitationCard key={`${c.citation_id}-${c.chunk_id}`} citation={c} />)}</div></section>}
  </article>;
}
