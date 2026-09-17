const reportStyles = `
@page { size: A4 portrait; margin: 16mm 15mm 18mm; }
html, body { margin: 0; padding: 0; background: #fff; color: #102a43; font-family: Arial, sans-serif; }
.compliance-print-report { color: #102a43; font-size: 10pt; line-height: 1.4; background: #fff; }
.print-report-title { margin: 0 0 5mm; padding-bottom: 3mm; border-bottom: 1.5pt solid #0b4f8a; }.print-report-title p { margin: 0 0 1mm; color: #0b4f8a; font-size: 9pt; font-weight: 700; letter-spacing: .04em; }.print-report-title h1 { margin: 0 0 1mm; color: #063970; font-size: 20pt; line-height: 1.15; }.print-report-title time { color: #486581; font-size: 8.5pt; }
.print-report-section { margin: 0 0 3mm; padding: 0 0 2mm; border-bottom: .5pt solid #cbd9e8; }.print-report-section h2 { margin: 0 0 1.5mm; color: #063970; font-size: 12pt; break-after: avoid; page-break-after: avoid; }.print-report-subsection { margin: 0 0 2mm; }.print-report-subsection:last-child { margin-bottom: 0; }.print-report-subsection h3 { margin: 0 0 1mm; color: #17466d; font-size: 10pt; break-after: avoid; page-break-after: avoid; }.print-report-subsection p, .print-report-subsection ol { margin: 0; }.print-report-subsection ol { padding-left: 5mm; }.print-report-subsection li { break-inside: avoid; page-break-inside: avoid; }
table { width: 100%; border-collapse: collapse; font-size: 9pt; } th, td { padding: 1.4mm 1.8mm; text-align: left; vertical-align: top; border-bottom: .4pt solid #cbd9e8; } thead { break-after: avoid; page-break-after: avoid; } thead th { color: #063970; border-bottom: 1pt solid #0b4f8a; } tbody th { width: 34%; font-weight: 700; } tr { break-inside: avoid; page-break-inside: avoid; }
.print-profile-note { margin: 2mm 0 0; color: #486581; font-size: 8.5pt; }.print-next-action { border-left: 2.5pt solid #0b4f8a; padding-left: 3mm; }.print-important { border-left: 2.5pt solid #e78b28; padding-left: 3mm; }.print-important, .print-next-action { break-inside: avoid; page-break-inside: avoid; }.print-report-disclaimer { margin: 4mm 0 2mm; padding: 2.5mm 3mm; border: 1pt solid #e78b28; font-weight: 700; break-inside: avoid; page-break-inside: avoid; }.compliance-print-report footer { margin-top: 3mm; color: #486581; font-size: 8.5pt; }
`;

export function printComplianceReport(report: HTMLElement, origin: HTMLButtonElement) {
  const frame = document.createElement('iframe');
  frame.className = 'compliance-print-frame';
  frame.title = 'Compliance Action Report print frame';
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
