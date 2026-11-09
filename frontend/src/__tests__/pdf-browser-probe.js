// Development-only synthetic browser probe. Not imported by production entrypoints.
// Invoke via Vite: (await import('/src/__tests__/pdf-browser-probe.js')).runPdfProbe()
import { jsPDF } from 'jspdf';
import html2canvas from 'html2canvas';
import { createPdfReportDocument } from '../utils/reportDocument';
import { renderReportPdf } from '../utils/reportExport';

export async function runPdfProbe({ rows = 250, columns = 8, longCell = false } = {}) {
  const names = Array.from({ length: columns }, (_, index) => `c${index}`);
  const records = Array.from({ length: rows }, (_, index) =>
    Object.fromEntries(
      names.map((name, column) => [name, column ? index * columns + column : `हिन्दी ${index}`]),
    ),
  );
  if (records.length) records[records.length - 1][names[0]] = 'FINAL ROW अंतिम पंक्ति';
  if (longCell && records.length) records[0][names[0]] = 'लंबा विवरण '.repeat(100);
  const source = {
    record: {
      question: 'Synthetic multilingual bounded PDF',
      columns: names,
      rows: records,
      row_count: rows,
    },
    presentation: {
      headline: 'Synthetic only — no provider or database',
      column_labels: Object.fromEntries(names.map((name, index) => [name, `Column ${index}`])),
    },
  };
  let report;
  const captures = [];
  const started = performance.now();
  try {
    report = createPdfReportDocument(source, {
      executive_summary: 'विवरण',
      rows_returned: 'पंक्तियाँ',
    });
    document.body.append(report);
    const pdf = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' });
    await renderReportPdf(pdf, report, async (element, options) => {
      const canvas = await html2canvas(element, options);
      captures.push({
        y: options.y,
        cssHeight: options.height,
        width: canvas.width,
        height: canvas.height,
        pixels: canvas.width * canvas.height,
      });
      return canvas;
    });
    const blob = pdf.output('blob');
    const url = URL.createObjectURL(blob);
    return {
      status: 'rendered',
      pages: pdf.getNumberOfPages(),
      bytes: blob.size,
      captures,
      milliseconds: performance.now() - started,
      previewUrl: url,
      releasePreview: () => URL.revokeObjectURL(url),
      note: 'Selected real-browser synthetic observation, not phone/ARM/RSS guarantee. Open preview and inspect first/last pages and Hindi/long cells.',
    };
  } catch (error) {
    return {
      status: 'rejected',
      message: error.message,
      captures,
      milliseconds: performance.now() - started,
    };
  } finally {
    report?.remove();
  }
}
