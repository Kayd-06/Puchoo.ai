# Bounded PDF export (F09)

Normal AskData and History exports use the shared bounded `renderReportPdf` path.
They do not rasterize the whole report and then slice a full-height canvas.

Before building the export DOM, limits reject more than2000rows,16columns,
10000cells,250000UTF-16 text units in total or8192units in a field (including
translated values/labels). No values are silently truncated; CSV is the fallback.
Tables use fixed layout and word wrapping, retaining browser font rendering for
Indian scripts rather than relying on jsPDF's Latin-only built-in text fonts.

Before **any capture**, layout and row geometry plan at most30pages. Unsupported
widths over1200CSSpx, oversized layout or excessive row-aware pagination reject.
Normal rows move intact to the next page; a row taller than a page is tiled with
continuous vertical coverage. Every capture specifies its own CSS width, height
and y-offset. Scale1.25 and a1.5million-pixel ceiling bound each returned bitmap
to6MB raw RGBA. The installed html2canvas1.4.1 allocation contract rounds the
requested scaled width/height down; returned dimensions are checked exactly.
Unrelated app subtrees (including animated canvases) are excluded from cloning.

Each bitmap is added sequentially and zero-sized before the next capture. Owned
clone iframes are removed even on capture/encoder failure; existing page callers
remove the export article in finally and offer CSV when export fails. No partial
PDF is saved after an error. Images/footers are retained in jsPDF as needed to
build the final document, so these limits are NOT an absolute process/RSS cap.
The underlying DOM/layout/font/renderer promises do not have a hard wall-clock
cancellation guarantee. No whole-document bitmap is used as an intermediate.

Deterministic tests verify pre-DOM rejection, accepted multilingual/zero values,
exact page rectangles, oversized rows, no unrelated canvas cloning, sequential
bitmap release, page-count/geometry limits and failure cleanup. They are DOM and
renderer-contract fixtures, NOT real PDF image-readability, phone RAM/latency or
browser/ARM measurements. A real-browser export of largest supported reports,
Indian-script long cells, page breaks, and actual peak-memory/latency remains a
release gate. Do not describe the6MB per-bitmap arithmetic as total export memory.
