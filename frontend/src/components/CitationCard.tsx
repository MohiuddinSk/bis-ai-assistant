import { useId, useState } from 'react';
import { openSourcePdf } from '../services/api';
import type { Citation } from '../types/chat';

export function CitationCard({ citation }: { citation: Citation }) {
  const [open, setOpen] = useState(false);
  const [pdfError, setPdfError] = useState('');
  const evidenceId = useId();
  const pages = citation.page_start === citation.page_end ? `Page ${citation.page_start ?? 'not available'}` : `Pages ${citation.page_start ?? '?'}–${citation.page_end ?? '?'}`;
  const openSource = async () => {
    if (!citation.source_filename) return;
    setPdfError('');
    try {
      await openSourcePdf(citation.source_filename, citation.page_start);
    } catch {
      setPdfError('Unable to open the source PDF. Please try again.');
    }
  };
  return <article className="citation-card">
    <div className="citation-meta"><span className="source-badge">Source {citation.citation_id}</span><span className="page-pill">{pages}</span></div>
    <p className="citation-filename">{citation.source_filename ?? 'Indexed document'}</p>
    <div className="citation-actions">
      <button className="evidence-toggle" aria-expanded={open} aria-controls={evidenceId} onClick={() => setOpen(!open)}>View evidence <span aria-hidden="true">{open ? '▴' : '▾'}</span></button>
      {citation.source_filename && <a className="pdf-link" href="#open-source-pdf" target="_blank" rel="noopener noreferrer" onClick={event => { event.preventDefault(); void openSource(); }} aria-label={`Open source PDF ${citation.source_filename}${citation.page_start ? ` at page ${citation.page_start}` : ''}`}>Open source PDF <span aria-hidden="true">↗</span></a>}
    </div>
    {pdfError && <p className="error" role="alert">{pdfError}</p>}
    {open && <section id={evidenceId} className="evidence-panel" aria-label="Extracted source text"><strong>Extracted source text</strong><p>{citation.excerpt}</p></section>}
  </article>;
}
