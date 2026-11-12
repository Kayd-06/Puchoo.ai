const numeric = (value) =>
  typeof value === 'number'
    ? Number.isFinite(value)
      ? value
      : null
    : typeof value === 'string' &&
        /^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(value.trim()) &&
        Number.isFinite(Number(value))
      ? Number(value)
      : null;
const dateValue = (value) =>
  typeof value === 'string' &&
  /^\d{4}-\d{2}-\d{2}(?:$|T| )/.test(value) &&
  Number.isFinite(Date.parse(value));
export function chartColumns(record) {
  const rows = record.rows || [];
  const types = {};
  for (const column of record.columns || []) {
    const values = rows
      .map((row) => row[column])
      .filter((v) => v !== null && v !== undefined && v !== '');
    types[column] =
      values.length && values.every(dateValue)
        ? 'date'
        : values.length && values.every((v) => numeric(v) !== null)
          ? 'number'
          : 'category';
  }
  return {
    types,
    measures: Object.keys(types).filter(
      (c) => types[c] === 'number' && !/(^id$|_id$|^id_|Id$|ID$)/.test(c),
    ),
    dimensions: Object.keys(types),
  };
}
export function chartData(record, x, y, aggregation = 'none', preserveObservations = false) {
  const { types } = chartColumns(record);
  if (preserveObservations && aggregation === 'none' && types[x] === 'number') {
    return (record.rows || [])
      .filter((row) => numeric(row[x]) !== null)
      .map((row) => ({ label: String(row[x]), x: numeric(row[x]), value: numeric(row[y]) }))
      .sort((a, b) => a.x - b.x);
  }
  const groups = new Map();
  for (const row of record.rows || []) {
    if (row[x] === null || row[x] === undefined || row[x] === '') continue;
    const key = String(row[x]);
    if (!groups.has(key))
      groups.set(key, { label: key, x: types[x] === 'number' ? numeric(row[x]) : key, values: [] });
    groups.get(key).values.push(numeric(row[y]));
  }
  if (aggregation === 'none' && [...groups.values()].some((g) => g.values.length > 1)) return [];
  const data = [...groups.values()].map((g) => {
    const values = g.values.filter((v) => v !== null);
    const sum = values.reduce((a, b) => a + b, 0);
    return {
      label: g.label,
      x: g.x,
      value:
        aggregation === 'count'
          ? g.values.length
          : !values.length
            ? null
            : aggregation === 'min'
              ? Math.min(...values)
              : aggregation === 'max'
                ? Math.max(...values)
                : aggregation === 'sum'
                  ? sum
                  : aggregation === 'average'
                    ? sum / values.length
                    : g.values[0],
    };
  });
  if (types[x] === 'date') data.sort((a, b) => Date.parse(a.label) - Date.parse(b.label));
  if (types[x] === 'number') data.sort((a, b) => a.x - b.x);
  return data;
}
export function chartTypes(data, xType, measureCount = 1) {
  const types = ['bar', 'horizontal'];
  if (xType === 'date' || xType === 'number') types.push('line', 'step', 'area');
  if (xType === 'number') types.push('scatter');
  const positive =
    data.length >= 2 &&
    data.every((d) => d.value !== null && d.value >= 0) &&
    data.some((d) => d.value > 0);
  if (xType === 'category' && positive) {
    if (data.length <= 8) types.push('pie', 'donut');
    if (data.length >= 3 && data.length <= 12) types.push('radar');
    types.push('treemap');
  }
  if (measureCount > 1) types.push('grouped', 'stacked', 'combo');
  return types;
}
export function defaultChart(record) {
  const { types, dimensions, measures } = chartColumns(record);
  if ((record.rows || []).length < 2 || !measures.length) return null;
  const y = measures[0];
  const x =
    dimensions.find((c) => types[c] === 'date') ||
    dimensions.find((c) => types[c] === 'category') ||
    dimensions.find((c) => c !== y && !/(^id$|_id$)/i.test(c));
  return x
    ? {
        x,
        y,
        type: types[x] === 'date' ? 'line' : types[x] === 'number' ? 'scatter' : 'bar',
        aggregation: 'none',
      }
    : null;
}

const COMPARISON_TYPES = ['grouped', 'stacked', 'combo'];
const AGGREGATIONS = ['none', 'sum', 'average', 'count', 'min', 'max'];
const SORTS = ['original', 'ascending', 'descending', 'label'];
const LIMITS = [10, 20, 50, 100, 500];

// One resolver for the on-screen chart and every export, so they cannot drift.
export function resolveChart(record, config) {
  const initial = defaultChart(record);
  if (!initial) return null;
  const saved = config && Object.keys(config).length ? config : initial;
  const { types, dimensions, measures } = chartColumns(record);
  const y = measures.includes(saved.y) ? saved.y : initial.y;
  const x =
    dimensions.includes(saved.x) && saved.x !== y ? saved.x : dimensions.find((c) => c !== y);
  const aggregation = AGGREGATIONS.includes(saved.aggregation) ? saved.aggregation : 'none';
  const raw = chartData(record, x, y, aggregation, saved.type === 'scatter');
  const secondaryOptions = measures.filter((c) => c !== y && c !== x);
  const secondary = secondaryOptions.includes(saved.secondary)
    ? saved.secondary
    : secondaryOptions[0];
  const options = chartTypes(raw, types[x], secondary && aggregation !== 'count' ? 2 : 1);
  const type = options.includes(saved.type) ? saved.type : options[0];
  const comparison = COMPARISON_TYPES.includes(type);
  const other = comparison
    ? new Map(chartData(record, x, secondary, aggregation).map((p) => [p.label, p.value]))
    : null;
  let data = raw.map((p) => (comparison ? { ...p, secondary: other.get(p.label) ?? null } : p));
  const sort = SORTS.includes(saved.sort) ? saved.sort : 'original';
  if (sort === 'label')
    data.sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }));
  else if (sort !== 'original')
    data.sort((a, b) =>
      a.value === null
        ? 1
        : b.value === null
          ? -1
          : sort === 'ascending'
            ? a.value - b.value
            : b.value - a.value,
    );
  const limit = LIMITS.includes(Number(saved.limit)) ? Number(saved.limit) : 50;
  const total = data.length;
  data = data.slice(0, limit);
  const drawable = data.some((p) => p.value !== null || (comparison && p.secondary !== null));
  return {
    initial,
    saved,
    types,
    dimensions,
    measures,
    x,
    y,
    aggregation,
    raw,
    secondaryOptions,
    secondary,
    options,
    type,
    comparison,
    sort,
    limit,
    data,
    total,
    drawable,
  };
}

// Returns the plotted points, or null when nothing can be drawn.
export function chartExportData(record, config) {
  const chart = resolveChart(record, config);
  if (!chart?.drawable) return null;
  const { x, y, secondary, aggregation, type, data, total, comparison } = chart;
  return { x, y, secondary: comparison ? secondary : null, aggregation, type, data, total };
}
