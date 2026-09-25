import { useId, useState } from 'react';
import { openSourcePdf } from '../services/api';
import type { Citation } from '../types/chat';
import { useLanguage } from '../i18n/LanguageContext';

export function CitationCard({ citation }: { citation: Citation }) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const [pdfError, setPdfError] = useState('');
  const evidenceId = useId();
  const pages = citation.page_start === citation.page_end ? `${t('page')} ${citation.page_start ?? t('pageUnavailable')}` : `${t('pages')} ${citation.page_start ?? '?'}–${citation.page_end ?? '?'}`;
  const openSource = async () => {
    if (!citation.source_filename) return;
    setPdfError('');
    try {
      await openSourcePdf(citation.source_filename, citation.page_start);
    } catch {
      setPdfError(t('pdfOpenError'));
    }
  };
  return <article className="citation-card">
    <div className="citation-meta"><span className="source-badge">{t('source')} {citation.citation_id}</span><span className="page-pill">{pages}</span></div>
    <p className="citation-filename">{citation.source_filename ?? t('source')}</p>
    <div className="citation-actions">
      <button className="evidence-toggle" aria-expanded={open} aria-controls={evidenceId} onClick={() => setOpen(!open)}>{t('viewEvidence')} <span aria-hidden="true">{open ? '▴' : '▾'}</span></button>
      {citation.source_filename && <a className="pdf-link" href="#open-source-pdf" target="_blank" rel="noopener noreferrer" onClick={event => { event.preventDefault(); void openSource(); }} aria-label={t('openSourcePdfAria').replace('{filename}', citation.source_filename).replace('{page}', citation.page_start ? ` ${t('page')} ${citation.page_start}` : '')}>{t('openSourcePdf')} <span aria-hidden="true">↗</span></a>}
    </div>
    {pdfError && <p className="error" role="alert">{pdfError}</p>}
    {open && <section id={evidenceId} className="evidence-panel" aria-label={t('extractedSourceText')}><strong>{t('extractedSourceText')}</strong><p>{citation.excerpt}</p></section>}
  </article>;
}
