import { afterEach, describe, expect, it, vi } from 'vitest';

import { buildCsv, csvCell, renderPdfHtml, renderReportPdf } from '../reportExport';

describe('csvCell', () => {
  it.each(['=SUM(A1:A9)', '+1+1', '-2+3', '@cmd', '\t=1', '\r=1'])(
    'neutralises a formula-looking value %j',
    (value) => {
      expect(csvCell(value)).toBe(`"'${value}"`);
    },
  );

  it('quotes plain values and escapes double quotes', () => {
    expect(csvCell('Alice "Al" Smith')).toBe('"Alice ""Al"" Smith"');
    expect(csvCell(42)).toBe('"42"');
    expect(csvCell(null)).toBe('""');
  });

  it('builds CRLF-separated rows', () => {
    expect(
      buildCsv([
        ['name', 'total'],
        ['=HYPERLINK("x")', 5],
      ]),
    ).toBe('"name","total"\r\n"\'=HYPERLINK(""x"")","5"');
  });
});

describe('renderPdfHtml', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('resolves with the document when jsPDF calls back', async () => {
    const doc = { save: vi.fn() };
    const pdf = { html: vi.fn((_el, options) => options.callback(doc)) };
    await expect(renderPdfHtml(pdf, {}, { margin: 1 })).resolves.toBe(doc);
    expect(pdf.html.mock.calls[0][1].margin).toBe(1);
  });

  it('rejects when html() throws or its promise rejects', async () => {
    const throwing = {
      html: () => {
        throw new Error('boom');
      },
    };
    await expect(renderPdfHtml(throwing, {}, {})).rejects.toThrow('boom');

    const rejecting = { html: () => Promise.reject(new Error('canvas failed')) };
    await expect(renderPdfHtml(rejecting, {}, {})).rejects.toThrow('canvas failed');
  });

  it('rejects instead of hanging when the callback never fires', async () => {
    vi.useFakeTimers();
    const pending = renderPdfHtml({ html: () => undefined }, {}, {}, 1000);
    vi.advanceTimersByTime(1000);
    await expect(pending).rejects.toThrow('PDF export timed out.');
  });
});

function pdfFixture() {
  return {
    internal: { pageSize: { getWidth: () => 842, getHeight: () => 595 } },
    addPage: vi.fn(),
    addImage: vi.fn(),
    setFontSize: vi.fn(),
    setTextColor: vi.fn(),
    text: vi.fn(),
  };
}
function reportFixture(height = 1600, width = 1000) {
  const report = document.createElement('article');
  report.getBoundingClientRect = () => ({ width, height, top: 0, left: -100000 });
  document.body.append(report);
  return report;
}
function canvasFixture(options) {
  return {
    width: Math.floor(options.width * options.scale),
    height: Math.floor(options.height * options.scale),
    toDataURL: () => 'data:image/png;base64,content',
  };
}
it('captures only bounded on-screen pages, excludes unrelated app canvases, and releases before next capture', async () => {
  const report = reportFixture(),
    pdf = pdfFixture(),
    canvases = [],
    boxes = [];
  const app = document.createElement('div');
  const animation = document.createElement('canvas');
  app.append(animation);
  document.body.append(app);
  const capture = vi.fn(async (element, options) => {
    expect(canvases.every((canvas) => canvas.width === 0 && canvas.height === 0)).toBe(true);
    expect(options.ignoreElements(app)).toBe(true);
    expect(options.ignoreElements(animation)).toBe(true);
    expect(options.ignoreElements(report)).toBe(false);
    expect(options.ignoreElements(document.body)).toBe(false);
    const clone = document.createElement('article');
    options.onclone(null, clone);
    expect(clone.style.left).toBe('0px');
    expect(clone.style.position).toBe('absolute');
    const canvas = canvasFixture(options);
    expect(canvas.width * canvas.height).toBeLessThanOrEqual(1500000);
    canvases.push(canvas);
    boxes.push([options.y, options.height]);
    return canvas;
  });
  try {
    await renderReportPdf(pdf, report, capture);
  } finally {
    report.remove();
    app.remove();
  }
  expect(boxes).toEqual([
    [0, 667],
    [667, 667],
    [1334, 266],
  ]);
  expect(canvases.every((canvas) => canvas.width === 0 && canvas.height === 0)).toBe(true);
  expect(pdf.addImage).toHaveBeenCalledTimes(3);
  expect(pdf.addPage).toHaveBeenCalledTimes(2);
  expect(pdf.text).toHaveBeenCalledWith('Page 1 of 3', 814, 577, { align: 'right' });
});
it('plans whole rows before capture but makes progress through an oversized multilingual row', async () => {
  const report = reportFixture();
  const row = document.createElement('tr');
  row.getBoundingClientRect = () => ({ top: 600, bottom: 1600 });
  report.append(row);
  const capture = vi.fn(async (_e, options) => canvasFixture(options));
  try {
    await renderReportPdf(pdfFixture(), report, capture);
  } finally {
    report.remove();
  }
  expect(capture.mock.calls.map(([, options]) => [options.y, options.height])).toEqual([
    [0, 600],
    [600, 667],
    [1267, 333],
  ]);
});
it.each([
  [1000000, 1000],
  [1600, 4000],
  [0, 1000],
])('rejects unsupported layout before any raster allocation (%s,%s)', async (height, width) => {
  const report = reportFixture(height, width),
    capture = vi.fn();
  try {
    await expect(renderReportPdf(pdfFixture(), report, capture)).rejects.toThrow(/PDF/);
  } finally {
    report.remove();
  }
  expect(capture).not.toHaveBeenCalled();
});
it('releases captured canvas and owned clone on PDF encoder failure', async () => {
  const report = reportFixture(),
    pdf = pdfFixture(),
    frame = { remove: vi.fn() };
  let canvas;
  pdf.addImage.mockImplementation(() => {
    throw new Error('encoder failed');
  });
  const capture = vi.fn(async (_e, options) => {
    options.onclone({ defaultView: { frameElement: frame } }, document.createElement('article'));
    canvas = canvasFixture(options);
    return canvas;
  });
  try {
    await expect(renderReportPdf(pdf, report, capture)).rejects.toThrow('encoder failed');
  } finally {
    report.remove();
  }
  expect(canvas.width).toBe(0);
  expect(canvas.height).toBe(0);
  expect(frame.remove).toHaveBeenCalledOnce();
  expect(capture).toHaveBeenCalledOnce();
});
it('removes owned clone if capture rejects before returning a canvas', async () => {
  const report = reportFixture(),
    frame = { remove: vi.fn() };
  try {
    await expect(
      renderReportPdf(pdfFixture(), report, async (_e, options) => {
        options.onclone(
          { defaultView: { frameElement: frame } },
          document.createElement('article'),
        );
        throw new Error('capture failed');
      }),
    ).rejects.toThrow('capture failed');
  } finally {
    report.remove();
  }
  expect(frame.remove).toHaveBeenCalledOnce();
});
it('rejects and releases a renderer that violates requested dimensions', async () => {
  const report = reportFixture(),
    canvas = { width: 10000, height: 10000 };
  try {
    await expect(renderReportPdf(pdfFixture(), report, async () => canvas)).rejects.toThrow(
      'dimensions',
    );
  } finally {
    report.remove();
  }
  expect(canvas.width).toBe(0);
  expect(canvas.height).toBe(0);
});
