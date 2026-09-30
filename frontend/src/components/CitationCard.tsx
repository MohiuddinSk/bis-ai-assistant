import { useId, useState } from 'react';
import { openSourcePdf } from '../services/api';
import type { Citation } from '../types/chat';
import { useLanguage } from '../i18n/LanguageContext';
import { officialEvidenceLabels } from '../i18n/translations';

function officialBisUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname === 'www.bis.gov.in'
      && !url.username && !url.password && !url.port ? url.toString() : null;
  } catch {
    return null;
  }
}

export function CitationCard({ citation }: { citation: Citation }) {
  const { t, language } = useLanguage();
  const [open, setOpen] = useState(false);
  const [pdfError, setPdfError] = useState('');
  const evidenceId = useId();
  const labels = officialEvidenceLabels[language];
  const isHtml = citation.source_type === 'html';
  const officialUrl = isHtml ? officialBisUrl(citation.source_url) : null;
  const pages = isHtml ? `${labels.section}: ${citation.source_section ?? citation.source_title ?? t('source')}` : citation.page_start === citation.page_end ? `${t('page')} ${citation.page_start ?? t('pageUnavailable')}` : `${t('pages')} ${citation.page_start ?? '?'}–${citation.page_end ?? '?'}`;
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
    <p className="citation-filename">{citation.source_title ?? citation.source_filename ?? t('source')}</p>
    {isHtml && (citation.source_last_updated || citation.retrieved_at) && <p className="citation-provenance">{citation.source_last_updated && `${labels.updated}: ${citation.source_last_updated}`}{citation.source_last_updated && citation.retrieved_at && ' · '}{citation.retrieved_at && `${labels.checked}: ${citation.retrieved_at}`}</p>}
    <div className="citation-actions">
      <button className="evidence-toggle" aria-expanded={open} aria-controls={evidenceId} onClick={() => setOpen(!open)}>{t('viewEvidence')} <span aria-hidden="true">{open ? '▴' : '▾'}</span></button>
      {citation.source_filename && <a className="pdf-link" href="#open-source-pdf" target="_blank" rel="noopener noreferrer" onClick={event => { event.preventDefault(); void openSource(); }} aria-label={t('openSourcePdfAria').replace('{filename}', citation.source_filename).replace('{page}', citation.page_start ? ` ${t('page')} ${citation.page_start}` : '')}>{t('openSourcePdf')} <span aria-hidden="true">↗</span></a>}
      {officialUrl && <a className="pdf-link" href={officialUrl} target="_blank" rel="noopener noreferrer" aria-label={labels.openAria.replace('{title}', citation.source_title ?? t('source')).replace('{section}', citation.source_section ?? '')}>{labels.open} <span aria-hidden="true">↗</span></a>}
    </div>
    {pdfError && <p className="error" role="alert">{pdfError}</p>}
    {open && <section id={evidenceId} className="evidence-panel" aria-label={t('extractedSourceText')}><strong>{t('extractedSourceText')}</strong><p>{citation.excerpt}</p></section>}
  </article>;
}
