import { afterEach, expect, it, vi } from 'vitest';
import { createPdfReportDocument, assertPdfReportBounds } from '../reportDocument';
afterEach(() => vi.restoreAllMocks());
function result(rows = [{ amount: 0 }]) {
  return {
    record: { question: 'खर्च रिपोर्ट', columns: ['amount'], rows },
    presentation: { headline: 'सारांश', column_labels: { amount: 'राशि' }, display_rows: rows },
  };
}
it('preserves localized text and zero cells without unsafe HTML insertion', () => {
  const source = result([{ amount: 0 }, { amount: 'हिन्दी <script>not markup</script>' }]);
  const report = createPdfReportDocument(source, {
    executive_summary: 'विवरण',
    rows_returned: 'पंक्तियाँ',
  });
  expect(report.textContent).toContain('राशि');
  expect(report.querySelector('tbody td').textContent).toBe('0');
  expect(report.querySelector('script')).toBeNull();
  expect(report.textContent).toContain('<script>not markup</script>');
  expect(report.querySelector('table').style.tableLayout).toBe('fixed');
});
it.each(['rows', 'columns', 'cells', 'field', 'total', 'translation', 'label'])(
  'rejects %s overflow before constructing report DOM',
  (kind) => {
    const source = result();
    const labels = {};
    if (kind === 'rows') source.record.rows = Array.from({ length: 2001 }, () => ({ amount: 1 }));
    if (kind === 'columns') source.record.columns = Array.from({ length: 17 }, (_, i) => String(i));
    if (kind === 'cells') {
      source.record.columns = Array.from({ length: 11 }, (_, i) => String(i));
      source.record.rows = Array.from({ length: 1000 }, () => ({}));
    }
    if (kind === 'field') source.presentation.headline = 'x'.repeat(8193);
    if (kind === 'total') {
      source.record.rows = Array.from({ length: 31 }, () => ({ amount: 'x'.repeat(8192) }));
      source.presentation.display_rows = source.record.rows;
    }
    if (kind === 'translation') source.presentation.display_rows = [{ amount: 'ह'.repeat(8193) }];
    if (kind === 'label') labels.executive_summary = 'x'.repeat(8193);
    const create = vi.spyOn(document, 'createElement');
    expect(() => createPdfReportDocument(source, labels)).toThrow(/PDF/);
    expect(create).not.toHaveBeenCalled();
  },
);
it('permits the supported maximum cell count without mutating values', () => {
  const source = {
    record: {
      question: 'Synthetic',
      columns: Array.from({ length: 10 }, (_, i) => String(i)),
      rows: Array.from({ length: 1000 }, () => ({})),
    },
  };
  expect(() => assertPdfReportBounds(source)).not.toThrow();
  expect(source.record.rows).toHaveLength(1000);
});
