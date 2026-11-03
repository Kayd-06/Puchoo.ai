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

// Capture in a separate document so the hidden export source and app theme cannot
// move the report outside the canvas. Keep browser fonts for Indian languages.
export async function renderReportPdf(pdf, element, capture) {
  await document.fonts?.ready;
  const canvas = await capture(element, {
    scale: 1.5,
    backgroundColor: '#ffffff',
    windowWidth: 1200,
    scrollX: 0,
    scrollY: 0,
    onclone: (_document, clone) => {
      Object.assign(clone.style, {
        position: 'absolute',
        left: '0px',
        top: '0px',
        margin: '0',
        transform: 'none',
        opacity: '1',
        visibility: 'visible',
      });
    },
  });
  if (!canvas.width || !canvas.height) throw new Error('The report could not be rendered.');
  const width = pdf.internal.pageSize.getWidth();
  const height = pdf.internal.pageSize.getHeight();
  const margin = 28;
  const contentWidth = width - margin * 2;
  const pagePixels = Math.floor(((height - 70) * canvas.width) / contentWidth);
  const origin = element.getBoundingClientRect();
  const ratio = origin.width ? canvas.width / origin.width : 1;
  const rows = [...element.querySelectorAll('tr')].map((row) => {
    const bounds = row.getBoundingClientRect();
    return {
      top: Math.floor((bounds.top - origin.top) * ratio),
      bottom: Math.ceil((bounds.bottom - origin.top) * ratio),
    };
  });
  const pages = [];
  for (let start = 0; start < canvas.height;) {
    let end = Math.min(start + pagePixels, canvas.height);
    const crossing = rows.find((row) => row.top < end && row.bottom > end);
    if (crossing && crossing.top > start) end = crossing.top;
    pages.push({ start, height: end - start });
    start = end;
  }
  const pageCount = pages.length;
  for (let page = 0; page < pageCount; page += 1) {
    if (page) pdf.addPage();
    const slice = document.createElement('canvas');
    slice.width = canvas.width;
    slice.height = pages[page].height;
    const context = slice.getContext('2d');
    if (!context) throw new Error('PDF rendering is unavailable.');
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, slice.width, slice.height);
    context.drawImage(
      canvas,
      0,
      pages[page].start,
      slice.width,
      slice.height,
      0,
      0,
      slice.width,
      slice.height,
    );
    pdf.addImage(
      slice.toDataURL('image/png'),
      'PNG',
      margin,
      margin,
      contentWidth,
      (slice.height * contentWidth) / slice.width,
    );
    pdf.setFontSize(9);
    pdf.setTextColor(85, 105, 125);
    pdf.text('Puchoo.si | Intelligence report', margin, height - 18);
    pdf.text(`Page ${page + 1} of ${pageCount}`, width - margin, height - 18, { align: 'right' });
  }
  return pdf;
}
