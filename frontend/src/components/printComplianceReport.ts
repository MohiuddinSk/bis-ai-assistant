const reportStyles = `
.compliance-print-report .passport-heading { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(47mm, .8fr); grid-template-areas: "identity status" "metadata notice"; gap: 3mm 5mm; align-items: start; margin: 0 0 4mm; padding: 0 0 3mm; border-bottom: 1.5pt solid #0b4f8a; break-inside: avoid; page-break-inside: avoid; }.compliance-print-report .passport-identity { grid-area: identity; min-width: 0; }.compliance-print-report .passport-identity .eyebrow { margin: 0 0 1mm; color: #0b4f8a; font-size: 9pt; font-weight: 700; letter-spacing: .04em; }.compliance-print-report .passport-identity h2 { margin: 0; color: #063970; font-size: 20pt; line-height: 1.15; }.compliance-print-report .passport-status { grid-area: status; justify-self: start; margin: 0; padding: 1mm 2mm; border-radius: 999px; font-weight: 700; line-height: 1.35; }.compliance-print-report .passport-status.available { background: #d7f3e3; color: #14532d; }.compliance-print-report .passport-status.needs_information { background: #fff1c2; color: #7c4a03; }.compliance-print-report .passport-status.needs_verification { background: #fde2e2; color: #8b1e1e; }.compliance-print-report .passport-metadata { grid-area: metadata; display: grid; grid-template-columns: minmax(32mm, 42%) minmax(0, 1fr); gap: .8mm 2mm; margin: 0; font-size: 9pt; }.compliance-print-report .passport-metadata dt { font-weight: 700; }.compliance-print-report .passport-metadata dd { min-width: 0; margin: 0; overflow-wrap: anywhere; }.compliance-print-report .passport-report-id { white-space: nowrap; font-variant-numeric: tabular-nums; letter-spacing: .02em; }.compliance-print-report .passport-notice { grid-area: notice; margin: 0; min-width: 0; color: #486581; font-size: 8.5pt; line-height: 1.4; overflow-wrap: anywhere; }.compliance-print-report .passport-section { margin: 0 0 3mm; padding: 0 0 2mm; border-top: 0; border-bottom: .5pt solid #cbd9e8; }.compliance-print-report .passport-section h2 { margin: 0 0 1.5mm; color: #063970; font-size: 12pt; break-after: avoid; page-break-after: avoid; }.compliance-print-report .passport-section-label { margin: 0 0 1.5mm; color: #486581; font-size: 9pt; font-weight: 700; }.compliance-print-report .passport-user-provided { margin: 0 0 1.5mm; color: #486581; font-size: 8.5pt; }.compliance-print-report .passport-profile dl { display: grid; grid-template-columns: minmax(32mm, 36%) minmax(0, 1fr); gap: 1.2mm 3mm; margin: 0; font-size: 9pt; }.compliance-print-report .passport-profile dt { font-weight: 700; }.compliance-print-report .passport-profile dt, .compliance-print-report .passport-profile dd { min-width: 0; margin: 0; overflow-wrap: anywhere; }.compliance-print-report .passport-subsection { margin: 0 0 2mm; }.compliance-print-report .passport-subsection h3 { margin: 0 0 1mm; color: #17466d; font-size: 10pt; }.compliance-print-report .passport-subsection p, .compliance-print-report .passport-subsection ol { margin: 0; }.compliance-print-report .passport-source { padding: 1.5mm 0; border-bottom: .4pt solid #cbd9e8; }.compliance-print-report .passport-source p { margin: 0 0 1mm; }.compliance-print-report .passport-source p:last-child { margin-bottom: 0; }
@page { size: A4 portrait; margin: 16mm 15mm 18mm; }
html, body { margin: 0; padding: 0; background: #fff; color: #102a43; font-family: Arial, sans-serif; }
.compliance-print-report { color: #102a43; font-size: 10pt; line-height: 1.4; background: #fff; }
.print-report-title { margin: 0 0 5mm; padding-bottom: 3mm; border-bottom: 1.5pt solid #0b4f8a; }.print-report-title p { margin: 0 0 1mm; color: #0b4f8a; font-size: 9pt; font-weight: 700; letter-spacing: .04em; }.print-report-title h1 { margin: 0 0 1mm; color: #063970; font-size: 20pt; line-height: 1.15; }.print-report-title time { color: #486581; font-size: 8.5pt; }
.print-report-section { margin: 0 0 3mm; padding: 0 0 2mm; border-bottom: .5pt solid #cbd9e8; }.print-report-section h2 { margin: 0 0 1.5mm; color: #063970; font-size: 12pt; break-after: avoid; page-break-after: avoid; }.print-report-subsection { margin: 0 0 2mm; }.print-report-subsection:last-child { margin-bottom: 0; }.print-report-subsection h3 { margin: 0 0 1mm; color: #17466d; font-size: 10pt; break-after: avoid; page-break-after: avoid; }.print-report-subsection p, .print-report-subsection ol { margin: 0; }.print-report-subsection ol { padding-left: 5mm; }.print-report-subsection li { break-inside: avoid; page-break-inside: avoid; }
table { width: 100%; border-collapse: collapse; font-size: 9pt; } th, td { padding: 1.4mm 1.8mm; text-align: left; vertical-align: top; border-bottom: .4pt solid #cbd9e8; } thead { break-after: avoid; page-break-after: avoid; } thead th { color: #063970; border-bottom: 1pt solid #0b4f8a; } tbody th { width: 34%; font-weight: 700; } tr { break-inside: avoid; page-break-inside: avoid; }
.print-profile-note { margin: 2mm 0 0; color: #486581; font-size: 8.5pt; }.print-next-action { border-left: 2.5pt solid #0b4f8a; padding-left: 3mm; }.print-important { border-left: 2.5pt solid #e78b28; padding-left: 3mm; }.print-important, .print-next-action { break-inside: avoid; page-break-inside: avoid; }.print-report-disclaimer { margin: 4mm 0 2mm; padding: 2.5mm 3mm; border: 1pt solid #e78b28; font-weight: 700; break-inside: avoid; page-break-inside: avoid; }.compliance-print-report footer { margin-top: 3mm; color: #486581; font-size: 8.5pt; }
`;

export function printComplianceReport(report: HTMLElement, origin: HTMLButtonElement, title = 'Compliance Action Report') {
  const frame = document.createElement('iframe');
  frame.className = 'compliance-print-frame';
  frame.title = `${title} print frame`;
  frame.setAttribute('aria-hidden', 'true');
  frame.style.cssText = 'position:fixed;width:1px;height:1px;right:0;bottom:0;border:0;opacity:0;pointer-events:none;';
  let cleaned = false;
  let fallback: number | undefined;
  const cleanup = () => {
    if (cleaned) return;
    cleaned = true;
    if (fallback !== undefined) window.clearTimeout(fallback);
    frame.contentWindow?.removeEventListener('afterprint', cleanup);
    frame.remove();
    origin.focus({ preventScroll: true });
  };
  document.body.append(frame);
  const frameDocument = frame.contentDocument;
  const frameWindow = frame.contentWindow;
  if (!frameDocument || !frameWindow) { cleanup(); return; }
  const style = frameDocument.createElement('style');
  style.textContent = reportStyles;
  frameDocument.head.append(style);
  frameDocument.body.append(report.cloneNode(true));
  const begin = async () => {
    try {
      await frameDocument.fonts?.ready;
    } catch { /* Printing remains usable when the browser cannot report font readiness. */ }
    await new Promise<void>((resolve) => {
      window.requestAnimationFrame(() => resolve());
    });
    if (cleaned) return;
    frameWindow.addEventListener('afterprint', cleanup, { once: true });
    fallback = window.setTimeout(cleanup, 30000);
    frameWindow.print();
  };
  void begin();
}
