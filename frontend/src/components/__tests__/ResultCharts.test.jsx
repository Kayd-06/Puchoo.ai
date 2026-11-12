import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import ResultCharts from '../ResultCharts';
vi.mock('recharts', async (importOriginal) => {
  const actual = await importOriginal();
  const { cloneElement } = await import('react');
  return {
    ...actual,
    ResponsiveContainer: ({ children }) => cloneElement(children, { width: 600, height: 300 }),
  };
});
const record = {
  columns: ['region', 'sales', 'margin'],
  rows: [
    { region: 'East', sales: 20, margin: 2 },
    { region: 'West', sales: 30, margin: 3 },
    { region: 'South', sales: 15, margin: 1 },
  ],
  truncated: true,
  row_count: 2,
};
it('shows a chart, partial result notice, compatible options, and emits saved configuration', () => {
  const save = vi.fn();
  render(<ResultCharts record={record} onConfigChange={save} />);
  expect(screen.getByRole('img')).toHaveAccessibleName(/bar chart of sales by region/i);
  expect(screen.getByText(/Partial results/)).toBeInTheDocument();
  expect(screen.queryByRole('option', { name: 'Scatter' })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Chart type'), { target: { value: 'donut' } });
  expect(screen.getByRole('img')).toHaveAccessibleName(/donut chart/);
  expect(save).toHaveBeenLastCalledWith({
    x: 'region',
    y: 'sales',
    type: 'donut',
    aggregation: 'none',
  });
});
it('restores configuration and renders no chart for text-only data', () => {
  const { rerender } = render(
    <ResultCharts
      record={record}
      config={{ x: 'sales', y: 'margin', type: 'scatter', aggregation: 'none' }}
    />,
  );
  expect(screen.getByLabelText('Chart type')).toHaveValue('scatter');
  rerender(<ResultCharts record={{ columns: ['name'], rows: [{ name: 'A' }, { name: 'B' }] }} />);
  expect(screen.queryByRole('region', { name: 'Result visualization' })).not.toBeInTheDocument();
});
it('explains duplicate categories until the user chooses aggregation', () => {
  render(
    <ResultCharts
      record={{
        ...record,
        rows: [
          { region: 'East', sales: 20 },
          { region: 'East', sales: 30 },
        ],
      }}
    />,
  );
  expect(screen.getByText(/Repeated categories need/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Download chart' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Advanced settings' }));
  fireEvent.change(screen.getByLabelText('Aggregation'), { target: { value: 'sum' } });
  expect(screen.getByRole('img')).toBeInTheDocument();
});
it('supports comparison charts, sorting, limits and resetting to the recommendation', () => {
  render(<ResultCharts record={record} />);
  fireEvent.change(screen.getByLabelText('Chart type'), { target: { value: 'grouped' } });
  expect(screen.getByLabelText('Compare with')).toHaveValue('margin');
  expect(screen.getByRole('img')).toHaveAccessibleName(/sales.*margin/);
  fireEvent.click(screen.getByRole('button', { name: 'Advanced settings' }));
  fireEvent.change(screen.getByLabelText('Sort by'), { target: { value: 'descending' } });
  fireEvent.change(screen.getByLabelText('Show points'), { target: { value: '10' } });
  fireEvent.click(screen.getByRole('button', { name: /Reset chart/i }));
  expect(screen.getByLabelText('Chart type')).toHaveValue('bar');
  expect(screen.getByRole('button', { name: 'Advanced settings' })).toHaveAttribute(
    'aria-expanded',
    'false',
  );
  fireEvent.click(screen.getByRole('button', { name: 'Advanced settings' }));
  expect(screen.getByLabelText('Sort by')).toHaveValue('original');
});
it('renders every eligible chart family', () => {
  const { rerender } = render(<ResultCharts record={record} />);
  for (const type of ['horizontal', 'pie', 'radar', 'treemap', 'grouped', 'stacked', 'combo']) {
    rerender(
      <ResultCharts
        record={record}
        config={{ x: 'region', y: 'sales', secondary: 'margin', type, aggregation: 'none' }}
      />,
    );
    expect(screen.getByRole('img')).toHaveAccessibleName(new RegExp(`${type} chart`));
  }
});
it('limits the sorted data and explicitly discloses omitted chart points', () => {
  const many = {
    columns: ['region', 'sales'],
    rows: Array.from({ length: 60 }, (_, i) => ({ region: `Region ${i}`, sales: i })),
  };
  render(<ResultCharts record={many} />);
  expect(screen.getByRole('img')).toHaveAccessibleName(/Showing 50 of 60 points/);
  expect(screen.getByText(/Showing 50 of 60 points after sorting/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Advanced settings' }));
  fireEvent.change(screen.getByLabelText('Sort by'), { target: { value: 'descending' } });
  fireEvent.change(screen.getByLabelText('Show points'), { target: { value: '10' } });
  expect(screen.getByRole('img')).toHaveAccessibleName(/Showing 10 of 60 points/);
  expect(screen.getByText('59')).toBeInTheDocument();
  expect(screen.getByText('50', { selector: 'strong' })).toBeInTheDocument();
});
it('renders an honest empty state when every X value is missing', () => {
  render(
    <ResultCharts
      record={{
        columns: ['region', 'sales'],
        rows: [
          { region: null, sales: 10 },
          { region: null, sales: 20 },
        ],
      }}
    />,
  );
  expect(screen.getByText('No chartable values for these axes')).toBeInTheDocument();
  expect(screen.queryByText(/Repeated categories need/)).not.toBeInTheDocument();
});
it('draws real horizontal bars and updates their values after changing aggregation', () => {
  const duplicate = {
    ...record,
    rows: [
      { region: 'East', sales: 10, margin: 1 },
      { region: 'East', sales: 20, margin: 2 },
      { region: 'West', sales: 8, margin: 3 },
    ],
  };
  const { container, rerender } = render(
    <ResultCharts
      record={duplicate}
      config={{ x: 'region', y: 'sales', type: 'horizontal', aggregation: 'sum' }}
    />,
  );
  const bars = container.querySelectorAll('.recharts-bar-rectangle path');
  expect(bars).toHaveLength(2);
  expect(Number(bars[0].getAttribute('width')) / Number(bars[1].getAttribute('width'))).toBeCloseTo(
    30 / 8,
  );
  rerender(
    <ResultCharts
      record={duplicate}
      config={{ x: 'region', y: 'sales', type: 'horizontal', aggregation: 'average' }}
    />,
  );
  const averaged = container.querySelectorAll('.recharts-bar-rectangle path');
  expect(
    Number(averaged[0].getAttribute('width')) / Number(averaged[1].getAttribute('width')),
  ).toBeCloseTo(15 / 8);
});
it('keeps everyday controls compact and reveals advanced settings on demand', () => {
  render(<ResultCharts record={record} />);
  expect(screen.getByLabelText('Chart type')).toBeVisible();
  expect(screen.getByLabelText('Metric')).toBeVisible();
  expect(screen.queryByLabelText('Aggregation')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Advanced settings' }));
  expect(screen.getByLabelText('Aggregation')).toBeVisible();
  expect(screen.getByLabelText('Group by')).toBeVisible();
});
it('offers direct aggregation actions when repeated categories prevent a chart', () => {
  render(
    <ResultCharts
      record={{
        ...record,
        rows: [
          { region: 'East', sales: 10 },
          { region: 'East', sales: 20 },
        ],
      }}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Sum values' }));
  expect(screen.getByRole('img')).toBeInTheDocument();
});

it('updates the actual chart and metric label when switching to row count and back', () => {
  const { container } = render(<ResultCharts record={record} />);
  fireEvent.change(screen.getByLabelText('Metric'), { target: { value: '__row_count' } });
  expect(screen.getByLabelText('Metric')).toHaveDisplayValue('Row count');
  expect(screen.getByRole('img')).toHaveAccessibleName(/Row count by region/);
  expect(container.querySelectorAll('.recharts-bar-rectangle path')).toHaveLength(3);
  fireEvent.change(screen.getByLabelText('Metric'), { target: { value: 'margin' } });
  expect(screen.getByRole('img')).toHaveAccessibleName(/margin by region/);
});
it('changes chart colors and preserves the choice when another setting changes', () => {
  const save = vi.fn();
  const { container } = render(<ResultCharts record={record} onConfigChange={save} />);
  fireEvent.click(screen.getByRole('button', { name: 'Chart color Teal' }));
  expect(screen.getByRole('button', { name: 'Chart color Teal' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  expect(container.querySelector('.recharts-bar-rectangle path')).toHaveAttribute(
    'fill',
    '#31b7a0',
  );
  fireEvent.change(screen.getByLabelText('Chart type'), { target: { value: 'donut' } });
  expect(save.mock.lastCall[0].colorIndex).toBe(1);
  fireEvent.click(screen.getByRole('button', { name: 'Reset chart' }));
  expect(screen.getByRole('button', { name: 'Chart color Blue' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});
