// Normalize the absolute SVG commands used by the wordmark into editable points.
export function parseLetterPath(path) {
  const tokens = path.match(/[MLHVQCZ]|-?\d*\.?\d+(?:e[-+]?\d+)?/gi);
  const points = [];
  const commands = [];
  let cursor = { x: 0, y: 0 };
  let start = cursor;
  let index = 0;
  let previous = '';
  while (index < tokens.length) {
    let op;
    if (/^[MLHVQCZ]$/.test(tokens[index])) {
      op = tokens[index++];
      previous = op;
    } else {
      op = previous === 'M' ? 'L' : previous;
    }
    if (op === 'Z') {
      commands.push({ op, indices: [] });
      cursor = start;
      continue;
    }
    const count = { M: 2, L: 2, H: 1, V: 1, Q: 4, C: 6 }[op];
    if (!count) throw new Error(`Unsupported wordmark path command: ${op}`);
    const values = tokens.slice(index, index + count).map(Number);
    index += count;
    const pairs = op === 'H' ? [values[0], cursor.y] : op === 'V' ? [cursor.x, values[0]] : values;
    const indices = [];
    for (let pair = 0; pair < pairs.length; pair += 2) {
      const point = { x: pairs[pair], y: pairs[pair + 1] };
      // Shared contour endpoints must deform together, including closed paths.
      let pointIndex = points.findIndex((p) => Math.hypot(p.x - point.x, p.y - point.y) < 0.001);
      if (pointIndex < 0) {
        pointIndex = points.length;
        points.push(point);
      }
      indices.push(pointIndex);
      cursor = point;
    }
    if (op === 'M') start = cursor;
    commands.push({ op: op === 'H' || op === 'V' ? 'L' : op, indices });
  }
  return { commands, points };
}

export function writeLetterPath(commands, points) {
  return commands
    .map(
      ({ op, indices }) =>
        op +
        indices
          .map((index) => `${points[index].x.toFixed(2)},${points[index].y.toFixed(2)}`)
          .join(' '),
    )
    .join('');
}

export function pointTarget(point, pointer, drag) {
  if (drag) {
    const distance = Math.hypot(point.x - drag.origin.x, point.y - drag.origin.y);
    const influence = Math.max(0, 1 - distance / 75) ** 2;
    const dx = Math.max(-45, Math.min(45, drag.x - drag.origin.x));
    const dy = Math.max(-45, Math.min(45, drag.y - drag.origin.y));
    return { x: point.x + dx * influence, y: point.y + dy * influence };
  }
  if (!pointer) return point;
  const dx = point.x - pointer.x;
  const dy = point.y - pointer.y;
  const distance = Math.hypot(dx, dy);
  const force = Math.max(0, 1 - distance / 55) ** 2 * 13;
  return {
    x: point.x + (dx / (distance || 1)) * force,
    y: point.y + (dy / (distance || 1)) * force,
  };
}
