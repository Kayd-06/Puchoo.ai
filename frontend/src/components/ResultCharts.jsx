import { useId, useRef, useState } from 'react';
import { ChartNoAxesCombined, Download, RotateCcw, SlidersHorizontal } from 'lucide-react';
import { chartColumns, chartData, chartTypes, defaultChart } from '../utils/resultCharts';
import ResultChartPlot, {
  chartColors,
  chartNames,
  comparisonTypes,
  formatChartNumber,
} from './ResultChartPlot';
import './resultCharts.css';

export default function ResultCharts({ record, presentation = {}, config, onConfigChange }) {
  const advancedId = useId();
  const [advanced, setAdvanced] = useState(false);
  const initial = defaultChart(record);
  const [localConfig, setLocalConfig] = useState(initial);
  const chartRef = useRef(null);
  const [downloadError, setDownloadError] = useState('');
  if (!initial) return null;
  const { types, dimensions, measures } = chartColumns(record);
  const saved = config || localConfig || initial;
  const colorIndex =
    Number.isInteger(saved.colorIndex) &&
    saved.colorIndex >= 0 &&
    saved.colorIndex < chartColors.length
      ? saved.colorIndex
      : 0;
  const colors = [...chartColors.slice(colorIndex), ...chartColors.slice(0, colorIndex)];
  const y = measures.includes(saved.y) ? saved.y : initial.y;
  const x =
    dimensions.includes(saved.x) && saved.x !== y ? saved.x : dimensions.find((c) => c !== y);
  const aggregation = ['none', 'sum', 'average', 'count', 'min', 'max'].includes(saved.aggregation)
    ? saved.aggregation
    : 'none';
  const raw = chartData(record, x, y, aggregation, saved.type === 'scatter');
  const secondaryOptions = measures.filter((c) => c !== y && c !== x);
  const secondary = secondaryOptions.includes(saved.secondary)
    ? saved.secondary
    : secondaryOptions[0];
  const options = chartTypes(raw, types[x], secondary && aggregation !== 'count' ? 2 : 1);
  const type = options.includes(saved.type) ? saved.type : options[0];
  const comparison = comparisonTypes.includes(type);
  const secondData = comparison
    ? new Map(chartData(record, x, secondary, aggregation).map((p) => [p.label, p.value]))
    : null;
  let data = raw.map((p) =>
    comparison ? { ...p, secondary: secondData.get(p.label) ?? null } : p,
  );
  const sort = ['original', 'ascending', 'descending', 'label'].includes(saved.sort)
    ? saved.sort
    : 'original';
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
  const limit = [10, 20, 50, 100, 500].includes(Number(saved.limit)) ? Number(saved.limit) : 50;
  const totalPoints = data.length;
  data = data.slice(0, limit);
  const label = (column) => presentation.column_labels?.[column] || column;
  const metricLabel = (column) =>
    aggregation === 'count'
      ? 'Row count'
      : aggregation === 'none'
        ? label(column)
        : `${{ sum: 'Sum', average: 'Average', min: 'Minimum', max: 'Maximum' }[aggregation]} of ${label(column)}`;
  const yLabel = metricLabel(y);
  const secondaryLabel = secondary ? metricLabel(secondary) : '';
  const update = (patch) => {
    const next = { x, y, type, aggregation, ...patch };
    // Retain optional controls without changing the shape of legacy configurations.
    for (const field of ['secondary', 'sort', 'limit', 'colorIndex'])
      if (!(field in patch) && saved[field] !== undefined) next[field] = saved[field];
    setLocalConfig(next);
    onConfigChange?.(next);
  };
  const reset = () => {
    setLocalConfig(initial);
    setAdvanced(false);
    onConfigChange?.(initial);
  };
  const download = () => {
    const svg = chartRef.current?.querySelector('svg.recharts-surface');
    if (!svg) {
      setDownloadError('Chart is still loading. Try again shortly.');
      return;
    }
    const clone = svg.cloneNode(true);
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    // Resolve theme variables so the downloaded SVG stays readable outside the app.
    const sources = [svg, ...svg.querySelectorAll('*')];
    const targets = [clone, ...clone.querySelectorAll('*')];
    sources.forEach((source, i) => {
      const computed = getComputedStyle(source);
      for (const property of ['fill', 'stroke', 'color', 'font-family', 'font-size'])
        targets[i].style.setProperty(property, computed.getPropertyValue(property));
    });
    clone.style.background = getComputedStyle(chartRef.current.closest('section')).backgroundColor;
    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.textContent = `${chartNames[type]}: ${yLabel}${comparison ? ` and ${secondaryLabel}` : ''} by ${label(x)}. Showing ${data.length} of ${totalPoints} points.${record.truncated ? ' Partial query results.' : ''}`;
    clone.prepend(title);
    const url = URL.createObjectURL(
      new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml' }),
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `puchoo-${type}-chart.svg`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setDownloadError('');
  };
  const drawable = data.some((p) => p.value !== null || (comparison && p.secondary !== null));
  const missingX = record.rows.filter(
    (row) => row[x] === null || row[x] === undefined || row[x] === '',
  ).length;
  const repeated = aggregation === 'none' && !raw.length && record.rows.length > missingX;
  const values = data.map((p) => p.value).filter((v) => v !== null);
  const min = values.length ? Math.min(...values) : null;
  const max = values.length ? Math.max(...values) : null;
  const categoryChart = ['pie', 'donut', 'radar', 'treemap'].includes(type);
  return (
    <section className="result-chart-card" aria-label="Result visualization">
      <div className="result-chart-heading">
        <div className="result-chart-title">
          <span className="result-chart-icon">
            <ChartNoAxesCombined size={20} />
          </span>
          <div>
            <span className="result-chart-overline">EXPLORE YOUR DATA</span>
            <h3>Visualize results</h3>
            <p>Compare patterns in the table above.</p>
          </div>
        </div>
        <div className="result-chart-actions">
          <button type="button" onClick={reset}>
            <RotateCcw size={14} />
            Reset chart
          </button>
          <button type="button" onClick={download} disabled={!drawable}>
            <Download size={14} />
            Download chart
          </button>
        </div>
      </div>
      <div className="result-chart-toolbar">
        <label>
          Chart type
          <select value={type} onChange={(e) => update({ type: e.target.value })}>
            {options.map((t) => (
              <option key={t} value={t}>
                {chartNames[t]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Metric
          <select
            value={aggregation === 'count' ? '__row_count' : y}
            onChange={(e) => {
              if (e.target.value === '__row_count') {
                update({ aggregation: 'count' });
                return;
              }
              update({
                y: e.target.value,
                ...(aggregation === 'count' ? { aggregation: 'none' } : {}),
                ...(e.target.value === x
                  ? { x: dimensions.find((c) => c !== e.target.value) }
                  : {}),
              });
            }}
          >
            {measures.map((c) => (
              <option key={c} value={c}>
                {label(c)}
              </option>
            ))}
            <option value="__row_count">Row count</option>
          </select>
        </label>
        {comparison && (
          <label>
            Compare with
            <select value={secondary} onChange={(e) => update({ secondary: e.target.value })}>
              {secondaryOptions.map((c) => (
                <option key={c} value={c}>
                  {label(c)}
                </option>
              ))}
            </select>
          </label>
        )}
        <button
          type="button"
          className="result-chart-advanced-toggle"
          aria-expanded={advanced}
          aria-controls={advancedId}
          onClick={() => setAdvanced((value) => !value)}
        >
          <SlidersHorizontal size={14} />
          Advanced settings
        </button>
      </div>
      <div className="result-chart-colors" role="group" aria-label="Chart color">
        <span>Chart color</span>
        <div className="result-chart-swatches">
          {chartColors.map((color, index) => (
            <button
              key={color}
              type="button"
              aria-label={`Chart color ${['Blue', 'Teal', 'Purple', 'Amber', 'Coral', 'Indigo', 'Green', 'Copper'][index]}`}
              aria-pressed={colorIndex === index}
              onClick={() => update({ colorIndex: index })}
              style={{ '--swatch': color }}
            />
          ))}
        </div>
      </div>
      {advanced && (
        <div
          id={advancedId}
          className="result-chart-controls"
          role="group"
          aria-label="Advanced chart settings"
        >
          <label>
            Group by
            <select value={x} onChange={(e) => update({ x: e.target.value })}>
              {dimensions
                .filter((c) => c !== y)
                .map((c) => (
                  <option key={c} value={c}>
                    {label(c)}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Aggregation
            <select value={aggregation} onChange={(e) => update({ aggregation: e.target.value })}>
              <option value="none">Keep table values</option>
              <option value="sum">Sum</option>
              <option value="average">Average</option>
              <option value="min">Minimum</option>
              <option value="max">Maximum</option>
              <option value="count">Row count</option>
            </select>
          </label>
          <label>
            Sort by
            <select value={sort} onChange={(e) => update({ sort: e.target.value })}>
              <option value="original">Table order / date</option>
              <option value="descending">Highest first</option>
              <option value="ascending">Lowest first</option>
              <option value="label">Category name</option>
            </select>
          </label>
          <label>
            Show points
            <select value={limit} onChange={(e) => update({ limit: Number(e.target.value) })}>
              {[10, 20, 50, 100, 500].map((n) => (
                <option key={n} value={n}>
                  Up to {n}
                </option>
              ))}
            </select>
          </label>
          <p className="result-chart-settings-note">
            These settings change only the chart. The table stays as returned.
          </p>
        </div>
      )}
      {record.truncated && (
        <p className="result-chart-notice" role="status">
          Partial results: this chart uses only the returned{' '}
          {record.row_count ?? record.rows.length} rows. Narrow your question to see the rest.
        </p>
      )}
      {totalPoints > limit && (
        <p className="result-chart-notice" role="status">
          Showing {data.length} of {totalPoints} points after sorting. Increase “Show points” to see
          more. The table keeps all returned rows.
        </p>
      )}
      {['pie', 'donut', 'treemap'].includes(type) && (
        <p className="result-chart-notice">
          Use this chart only when the categories form a meaningful whole.{' '}
          {type === 'treemap' ? 'Zero-value categories have no visible area.' : ''}
        </p>
      )}
      {type === 'stacked' && (
        <p className="result-chart-notice">
          Stack metrics only when they share a unit and their sum is meaningful.
        </p>
      )}
      {type === 'combo' && (
        <p className="result-chart-notice">
          Bars use the left axis; the line uses the right axis. Each axis has its own scale.
        </p>
      )}
      {drawable ? (
        <>
          <div className="result-chart-summary">
            <span>
              <strong>{data.length}</strong> plotted points
            </span>
            <span>
              Minimum <strong>{formatChartNumber(min)}</strong>
            </span>
            <span>
              Maximum <strong>{formatChartNumber(max)}</strong>
            </span>
          </div>
          <div className="result-chart-plot-heading">
            <h4>
              {yLabel}
              {comparison ? ` & ${secondaryLabel}` : ''} <span>by {label(x)}</span>
            </h4>
            <span>{chartNames[type]}</span>
          </div>
          <div
            ref={chartRef}
            className="result-chart-canvas"
            style={
              type === 'horizontal'
                ? { height: Math.max(340, Math.min(900, data.length * 32)) }
                : undefined
            }
            role="img"
            aria-label={`${type} chart of ${yLabel}${comparison ? ` and ${secondaryLabel}` : ''} by ${label(x)}. Showing ${data.length} of ${totalPoints} points. Exact values are available in the results table.`}
          >
            <ResultChartPlot
              key={`${type}:${x}:${y}:${secondary}:${aggregation}:${sort}:${limit}`}
              data={data}
              type={type}
              xLabel={label(x)}
              yLabel={yLabel}
              secondaryLabel={secondaryLabel}
              colors={colors}
            />
          </div>
          <div className="result-chart-legend" aria-label="Chart legend">
            {categoryChart ? (
              data.map((p, i) => (
                <span key={p.label}>
                  <i
                    style={{
                      background:
                        type === 'treemap' || type === 'radar'
                          ? colors[0]
                          : colors[i % colors.length],
                    }}
                  />
                  {p.label}: {formatChartNumber(p.value)}
                </span>
              ))
            ) : (
              <>
                <span>
                  <i style={{ background: colors[0] }} />
                  {yLabel}
                  {type === 'combo' ? ' (left axis)' : ''}
                </span>
                {comparison && (
                  <span>
                    <i style={{ background: colors[1] }} />
                    {secondaryLabel}
                    {type === 'combo' ? ' (right axis)' : ''}
                  </span>
                )}
              </>
            )}
          </div>
        </>
      ) : (
        <div className="result-chart-empty" role="status">
          <ChartNoAxesCombined size={30} />
          <strong>
            {repeated
              ? 'Choose how to combine repeated categories'
              : 'No chartable values for these axes'}
          </strong>
          <p>
            {repeated
              ? 'Repeated categories need an explicit aggregation. Choose Sum, Average, Minimum, Maximum, or Row count.'
              : 'Choose another X-axis or metric. Missing values are never replaced with zero.'}
          </p>
          {repeated && (
            <div className="result-chart-empty-actions">
              <button type="button" onClick={() => update({ aggregation: 'sum' })}>
                Sum values
              </button>
              <button type="button" onClick={() => update({ aggregation: 'average' })}>
                Average values
              </button>
              <button type="button" onClick={() => update({ aggregation: 'count' })}>
                Count rows
              </button>
            </div>
          )}
        </div>
      )}
      {downloadError && <p role="status">{downloadError}</p>}
      <p className="result-chart-note">
        Based on returned rows. Missing numeric values remain gaps;{' '}
        {missingX
          ? `${missingX} rows without an X-axis value are omitted.`
          : 'rows without an X-axis value are omitted.'}{' '}
        Aggregation applies only to this chart.
        {data.length > 30 && !categoryChart && !['horizontal', 'scatter'].includes(type)
          ? ' Drag the handles below the chart to zoom into a range.'
          : ''}
      </p>
    </section>
  );
}
