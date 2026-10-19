// Spreadsheet apps run a cell as a formula when it starts with one of these
// characters. Exported values come from user data, so neutralise them.
const FORMULA_PREFIX = /^[=+\-@\t\r]/;

export function csvCell(value) {
  const text = String(value ?? '');
  const safe = FORMULA_PREFIX.test(text) ? `'${text}` : text;
  return `"${safe.replaceAll('"', '""')}"`;
}

export function buildCsv(rows) {
  return rows.map((row) => row.map(csvCell).join(',')).join('\r\n');
}

// jsPDF's html() reports success through a callback only. Reject on errors or
// if the callback never fires, so the export button cannot stay stuck.
export function renderPdfHtml(pdf, element, options, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      fn(value);
    };
    const timer = window.setTimeout(
      () => finish(reject, new Error('PDF export timed out.')),
      timeoutMs,
    );
    try {
      const work = pdf.html(element, {
        ...options,
        callback: (documentPdf) => finish(resolve, documentPdf),
      });
      if (work && typeof work.catch === 'function') {
        work.catch((error) => finish(reject, error));
      }
    } catch (error) {
      finish(reject, error);
    }
  });
}
