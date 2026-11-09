export function saveBlob(blob, filename) {
  const href = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = href;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(href), 0);
}

export function reportFilename(question, extension) {
  const title =
    question
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 48) || 'report';
  return `puchoo-${title}.${extension}`;
}

export function reportTable(result) {
  const columns = result?.record?.columns || [];
  const labels = result?.presentation?.column_labels || {};
  const rows = result?.record?.rows || [];
  const displayRows = result?.presentation?.display_rows || rows;
  return {
    columns,
    labels: columns.map((column) => labels[column] || column),
    rows: rows.map((row, index) =>
      columns.map((column) => displayRows[index]?.[column] ?? row[column] ?? '—'),
    ),
  };
}

export const PDF_REPORT_LIMITS = Object.freeze({
  rows: 2000,
  columns: 16,
  cells: 10000,
  characters: 250000,
  fieldCharacters: 8192,
});
export function assertPdfReportBounds(result, labels = {}) {
  const columns = result?.record?.columns || [],
    rows = result?.record?.rows || [];
  if (
    rows.length > PDF_REPORT_LIMITS.rows ||
    columns.length > PDF_REPORT_LIMITS.columns ||
    rows.length * columns.length > PDF_REPORT_LIMITS.cells
  ) {
    throw new Error('Report exceeds PDF data limits. Download CSV instead.');
  }
  let characters = 0;
  const count = (value) => {
    const length = String(value ?? '').length;
    characters += length;
    if (length > PDF_REPORT_LIMITS.fieldCharacters || characters > PDF_REPORT_LIMITS.characters)
      throw new Error('Report exceeds PDF text limits. Download CSV instead.');
  };
  [
    labels.executive_summary,
    labels.rows_returned,
    result?.record?.question,
    result?.presentation?.headline,
    result?.presentation?.detail,
  ].forEach(count);
  columns.forEach((column) => count(result?.presentation?.column_labels?.[column] || column));
  rows.forEach((row, index) =>
    columns.forEach((column) =>
      count(result?.presentation?.display_rows?.[index]?.[column] ?? row[column] ?? '—'),
    ),
  );
}

export function createPdfReportDocument(result, labels) {
  assertPdfReportBounds(result, labels);
  const report = document.createElement('article');
  report.style.cssText =
    'position:fixed;left:-100000px;top:0;width:1040px;background:#fff;color:#172b36;padding:48px;font-family:Arial,"Noto Sans",sans-serif;font-size:13px;line-height:1.45;';
  const heading = document.createElement('h1');
  heading.textContent = 'Puchoo.si report';
  heading.style.cssText =
    'margin:0 0 20px;background:#142b49;border-left:8px solid #17b8a6;color:#fff;padding:24px 28px;font-size:30px;letter-spacing:-.5px;';
  const question = document.createElement('p');
  question.textContent = result.record.question;
  question.style.cssText = 'margin:12px 0 4px;font-size:18px;font-weight:600;';
  const metadata = document.createElement('p');
  metadata.textContent = `${result.record.row_count ?? 0} ${labels.rows_returned} · Generated ${new Date().toLocaleString()}`;
  metadata.style.cssText = 'margin:0 0 24px;color:#61727d;';
  const summary = document.createElement('section');
  summary.style.cssText =
    'margin:0 0 24px;border:1px solid #c5dcf5;border-left:5px solid #2676ca;border-radius:10px;background:#edf5ff;padding:20px 24px;';
  const summaryLabel = document.createElement('strong');
  summaryLabel.textContent = labels.executive_summary;
  const summaryText = document.createElement('p');
  summaryText.textContent = result.presentation?.headline || '';
  summaryText.style.cssText = 'margin:6px 0 0;font-size:17px;font-weight:600;';
  summary.append(summaryLabel, summaryText);

  const detail = result.presentation?.detail;
  if (detail) {
    const detailText = document.createElement('p');
    detailText.textContent = detail;
    detailText.style.cssText = 'margin:8px 0 0;color:#405662;';
    summary.append(detailText);
  }

  const tableData = reportTable(result);
  const table = document.createElement('table');
  table.style.cssText =
    'width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px;overflow-wrap:anywhere;word-break:break-word;';
  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  tableData.labels.forEach((label) => {
    const cell = document.createElement('th');
    cell.textContent = label;
    cell.style.cssText =
      'background:#176b79;color:#fff;padding:12px;text-align:left;font-weight:600;';
    headerRow.append(cell);
  });
  thead.append(headerRow);
  const tbody = document.createElement('tbody');
  tableData.rows.forEach((row, index) => {
    const tableRow = document.createElement('tr');
    row.forEach((value) => {
      const cell = document.createElement('td');
      cell.textContent = String(value);
      cell.style.cssText = `padding:9px 10px;border-bottom:1px solid #d9e3e8;background:${index % 2 ? '#edf5fa' : '#fff'};vertical-align:top;`;
      tableRow.append(cell);
    });
    tbody.append(tableRow);
  });
  table.append(thead, tbody);
  report.append(heading, question, metadata, summary, table);
  return report;
}
