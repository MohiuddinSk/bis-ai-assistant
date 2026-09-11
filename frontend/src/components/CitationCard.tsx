import { useId, useState } from 'react';
import type { Citation } from '../types/chat';

const apiBase = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

export function CitationCard({ citation }: { citation: Citation }) {
  const [open, setOpen] = useState(false);
  const evidenceId = useId();
  const pages = citation.page_start === citation.page_end ? `Page ${citation.page_start ?? 'not available'}` : `Pages ${citation.page_start ?? '?'}–${citation.page_end ?? '?'}`;
  const sourceUrl = citation.source_filename ? `${apiBase}/api/documents/${encodeURIComponent(citation.source_filename)}${citation.page_start ? `#page=${citation.page_start}` : ''}` : null;
  return <article className="citation-card">
    <div className="citation-meta"><span className="source-badge">Source {citation.citation_id}</span><span className="page-pill">{pages}</span></div>
    <p className="citation-filename">{citation.source_filename ?? 'Indexed document'}</p>
    <div className="citation-actions">
      <button className="evidence-toggle" aria-expanded={open} aria-controls={evidenceId} onClick={() => setOpen(!open)}>View evidence <span aria-hidden="true">{open ? '▴' : '▾'}</span></button>
      {sourceUrl && <a className="pdf-link" href={sourceUrl} target="_blank" rel="noopener noreferrer" aria-label={`Open source PDF ${citation.source_filename}${citation.page_start ? ` at page ${citation.page_start}` : ''}`}>Open source PDF <span aria-hidden="true">↗</span></a>}
    </div>
    {open && <section id={evidenceId} className="evidence-panel" aria-label="Extracted source text"><strong>Extracted source text</strong><p>{citation.excerpt}</p><details><summary>Technical details</summary><code>{citation.chunk_id}</code></details></section>}
  </article>;
}
