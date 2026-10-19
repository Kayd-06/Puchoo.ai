import { afterEach, describe, expect, it, vi } from 'vitest';

import { buildCsv, csvCell, renderPdfHtml } from '../reportExport';

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
