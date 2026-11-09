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

// Every capture starts with explicit bounded dimensions. Never rasterize the
// entire report first: page-sized canvases are released before the next capture.
export const PDF_CAPTURE_LIMITS = Object.freeze({
  maxWidth: 1200,
  maxPages: 30,
  maxPixels: 1500000,
  scale: 1.25,
});
export async function renderReportPdf(pdf, element, capture) {
  await document.fonts?.ready;
  const origin = element.getBoundingClientRect();
  const cssWidth = Math.ceil(origin.width),
    cssHeight = Math.ceil(origin.height);
  if (
    !Number.isFinite(cssWidth) ||
    !Number.isFinite(cssHeight) ||
    cssWidth <= 0 ||
    cssHeight <= 0 ||
    cssWidth > PDF_CAPTURE_LIMITS.maxWidth
  ) {
    throw new Error('Unsupported PDF layout. Download CSV instead.');
  }
  const width = pdf.internal.pageSize.getWidth(),
    height = pdf.internal.pageSize.getHeight();
  const margin = 28,
    contentWidth = width - margin * 2;
  const pixelWidth = Math.ceil(cssWidth * PDF_CAPTURE_LIMITS.scale);
  const pageCss = Math.floor(
    Math.min(
      ((height - 70) * cssWidth) / contentWidth,
      Math.floor(PDF_CAPTURE_LIMITS.maxPixels / pixelWidth) / PDF_CAPTURE_LIMITS.scale,
    ),
  );
  if (!Number.isFinite(pageCss) || pageCss < 1) throw new Error('Unsupported PDF page size.');
  // Bound page planning before retaining row geometry or invoking a renderer.
  if (cssHeight > pageCss * PDF_CAPTURE_LIMITS.maxPages)
    throw new Error('Report exceeds the PDF page budget. Download CSV instead.');
  const rowNodes = element.querySelectorAll('tr');
  if (rowNodes.length > 2001)
    throw new Error('Report exceeds the PDF row budget. Download CSV instead.');
  const rows = [...rowNodes].map((row) => {
    const bounds = row.getBoundingClientRect();
    return {
      top: Math.floor(bounds.top - origin.top),
      bottom: Math.ceil(bounds.bottom - origin.top),
    };
  });
  const pages = [];
  for (let start = 0; start < cssHeight;) {
    let end = Math.min(start + pageCss, cssHeight);
    const crossing = rows.find((row) => row.top < end && row.bottom > end);
    if (crossing && crossing.top > start) end = crossing.top;
    pages.push({ start, height: end - start });
    start = end;
    if (pages.length > PDF_CAPTURE_LIMITS.maxPages)
      throw new Error('Report exceeds the PDF page budget. Download CSV instead.');
  }
  for (let page = 0; page < pages.length; page += 1) {
    let canvas, cloneFrame;
    try {
      canvas = await capture(element, {
        scale: PDF_CAPTURE_LIMITS.scale,
        width: cssWidth,
        height: pages[page].height,
        x: 0,
        y: pages[page].start,
        backgroundColor: '#ffffff',
        windowWidth: 1200,
        scrollX: 0,
        scrollY: 0,
        removeContainer: true,
        ignoreElements: (node) =>
          document.body.contains(node) &&
          node !== element &&
          !node.contains(element) &&
          !element.contains(node),
        imageTimeout: 10000,
        onclone: (cloneDocument, clone) => {
          cloneFrame = cloneDocument?.defaultView?.frameElement;
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
      const expectedHeight = Math.floor(pages[page].height * PDF_CAPTURE_LIMITS.scale);
      if (
        !canvas.width ||
        !canvas.height ||
        canvas.width !== Math.floor(cssWidth * PDF_CAPTURE_LIMITS.scale) ||
        canvas.height !== expectedHeight ||
        canvas.width * canvas.height > PDF_CAPTURE_LIMITS.maxPixels
      ) {
        throw new Error('PDF renderer exceeded its bounded page dimensions.');
      }
      if (page) pdf.addPage();
      pdf.addImage(
        canvas.toDataURL('image/png'),
        'PNG',
        margin,
        margin,
        contentWidth,
        (canvas.height * contentWidth) / canvas.width,
      );
      pdf.setFontSize(9);
      pdf.setTextColor(85, 105, 125);
      pdf.text('Puchoo.si | Intelligence report', margin, height - 18);
      pdf.text(`Page ${page + 1} of ${pages.length}`, width - margin, height - 18, {
        align: 'right',
      });
    } finally {
      if (canvas) {
        canvas.width = 0;
        canvas.height = 0;
      }
      // Also remove our renderer's clone if a dependency fails before its cleanup.
      cloneFrame?.remove();
    }
  }
  return pdf;
}
