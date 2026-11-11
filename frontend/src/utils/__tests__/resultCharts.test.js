import { describe, expect, it } from 'vitest';
import { chartColumns, chartData, chartTypes, defaultChart } from '../resultCharts';

describe('query result charts', () => {
  it('recommends a chronological line and excludes IDs from measures', () => {
    const record = {
      columns: ['date', 'user_id', 'sales'],
      rows: [
        { date: '2026-02-01', user_id: 1, sales: 20 },
        { date: '2026-01-01', user_id: 2, sales: 10 },
      ],
    };
    expect(chartColumns(record).measures).toEqual(['sales']);
    expect(defaultChart(record)).toEqual({
      x: 'date',
      y: 'sales',
      type: 'line',
      aggregation: 'none',
    });
    expect(chartData(record, 'date', 'sales', 'none')[0].value).toBe(10);
  });
  it('preserves null gaps and numeric strings without using formatted display rows', () => {
    const record = {
      columns: ['region', 'revenue'],
      rows: [
        { region: 'A', revenue: '12.5' },
        { region: 'B', revenue: null },
      ],
    };
    expect(chartData(record, 'region', 'revenue', 'none').map((p) => p.value)).toEqual([
      12.5,
      null,
    ]);
  });
  it('requires explicit aggregation for duplicate categories', () => {
    const record = {
      columns: ['region', 'sales'],
      rows: [
        { region: 'A', sales: 10 },
        { region: 'A', sales: 20 },
      ],
    };
    expect(chartData(record, 'region', 'sales', 'none')).toEqual([]);
    expect(chartData(record, 'region', 'sales', 'average')[0].value).toBe(15);
    expect(chartData(record, 'region', 'sales', 'sum')[0].value).toBe(30);
  });
  it('restricts donut charts to small nonnegative complete datasets', () => {
    expect(chartTypes([{ value: -1 }, { value: 2 }], 'category')).not.toContain('donut');
    expect(chartTypes([{ value: null }, { value: 2 }], 'category')).not.toContain('donut');
    expect(chartTypes([{ value: 1 }, { value: 2 }], 'category')).toContain('donut');
  });
  it('does not chart text-only, empty, or single-value results', () => {
    expect(defaultChart({ columns: ['name'], rows: [{ name: 'A' }] })).toBeNull();
    expect(defaultChart({ columns: [], rows: [] })).toBeNull();
    expect(defaultChart({ columns: ['total'], rows: [{ total: 5 }] })).toBeNull();
  });
});

it('offers richer categorical charts and multi-metric comparisons only when supported', () => {
  const data = [{ value: 10 }, { value: 20 }, { value: 30 }];
  expect(chartTypes(data, 'category', 2)).toEqual(
    expect.arrayContaining([
      'bar',
      'horizontal',
      'pie',
      'donut',
      'radar',
      'treemap',
      'grouped',
      'stacked',
      'combo',
    ]),
  );
  expect(chartTypes(data, 'category', 1)).not.toContain('grouped');
  expect(chartTypes([{ value: -2 }, { value: 3 }], 'category', 2)).not.toContain('treemap');
  expect(chartTypes(data, 'date', 2)).toContain('step');
});
it('supports minimum and maximum without treating missing values as zero', () => {
  const record = {
    columns: ['region', 'sales'],
    rows: [
      { region: 'A', sales: null },
      { region: 'A', sales: 8 },
      { region: 'A', sales: 2 },
    ],
  };
  expect(chartData(record, 'region', 'sales', 'min')[0].value).toBe(2);
  expect(chartData(record, 'region', 'sales', 'max')[0].value).toBe(8);
});
it('preserves repeated numeric X coordinates for scatter observations', () => {
  const record = {
    columns: ['age', 'score'],
    rows: [
      { age: 20, score: 5 },
      { age: 20, score: 9 },
    ],
  };
  expect(chartData(record, 'age', 'score', 'none', true).map((p) => p.value)).toEqual([5, 9]);
});

it('exports the selected chart metrics, aggregation, ordering and point limit', async () => {
  const { chartExportData } = await import('../resultCharts');
  const record = {
    columns: ['region', 'sales', 'margin'],
    rows: Array.from({ length: 12 }, (_, i) => ({ region: `R${i}`, sales: i, margin: i * 2 })),
  };
  const result = chartExportData(record, {
    x: 'region',
    y: 'sales',
    secondary: 'margin',
    type: 'grouped',
    aggregation: 'none',
    sort: 'descending',
    limit: 10,
  });
  expect(result.total).toBe(12);
  expect(result.data).toHaveLength(10);
  expect(result.data[0]).toMatchObject({ label: 'R11', value: 11, secondary: 22 });
});
