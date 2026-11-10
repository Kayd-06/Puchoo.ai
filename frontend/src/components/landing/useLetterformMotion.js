import { useEffect } from 'react';
import { footerLetters, footerViewBox } from './footerLetterforms';
import { parseLetterPath, pointTarget, writeLetterPath } from './letterformMotion';

const geometry = footerLetters.map((glyph) => parseLetterPath(glyph.path));
const [, , width, height] = footerViewBox.split(' ').map(Number);

export function useLetterformMotion(svgRef, enabled) {
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || !enabled) return undefined;
    const letters = [...svg.querySelectorAll('.puchoo-letter-glyph')].map((group, index) => {
      const original = geometry[index];
      return {
        original,
        points: original.points.map((point) => ({ ...point, vx: 0, vy: 0 })),
        path: group.querySelector('.puchoo-letter-fill'),
        nodes: [...group.querySelectorAll('.puchoo-letter-node')].map((circle, node) => {
          const [x, y] = footerLetters[index].nodes[node];
          return {
            circle,
            hit: circle.previousElementSibling,
            index: original.points.findIndex((p) => Math.hypot(p.x - x, p.y - y) < 0.02),
          };
        }),
      };
    });
    let pointer = null;
    let drag = null;
    let frame = 0;
    let lastTime = null;

    function render() {
      letters.forEach((letter) => {
        letter.path.setAttribute('d', writeLetterPath(letter.original.commands, letter.points));
        letter.nodes.forEach(({ circle, hit, index }) => {
          const point = letter.points[index];
          for (const element of [circle, hit]) {
            element.setAttribute('cx', point.x.toFixed(2));
            element.setAttribute('cy', point.y.toFixed(2));
          }
        });
      });
    }
    function tick(time) {
      const dt = lastTime === null ? 1 : Math.min(2, Math.max(0.5, (time - lastTime) / 16.67));
      lastTime = time;
      frame = 0;
      let unsettled = false;
      letters.forEach((letter, letterIndex) => {
        letter.points.forEach((point, index) => {
          const target = pointTarget(
            letter.original.points[index],
            drag ? null : pointer,
            drag?.letter === letterIndex ? drag : null,
          );
          point.vx = (point.vx + (target.x - point.x) * 0.12 * dt) * Math.pow(0.7, dt);
          point.vy = (point.vy + (target.y - point.y) * 0.12 * dt) * Math.pow(0.7, dt);
          point.x += point.vx * dt;
          point.y += point.vy * dt;
          if (
            Math.abs(target.x - point.x) +
              Math.abs(target.y - point.y) +
              Math.abs(point.vx) +
              Math.abs(point.vy) >
            0.025
          )
            unsettled = true;
        });
      });
      render();
      if (unsettled) frame = window.requestAnimationFrame(tick);
      else lastTime = null;
    }
    function wake() {
      if (!frame) frame = window.requestAnimationFrame(tick);
    }
    function position(event) {
      const bounds = svg.getBoundingClientRect();
      if (!bounds.width || !bounds.height) return null;
      return {
        x: ((event.clientX - bounds.left) / bounds.width) * width,
        y: ((event.clientY - bounds.top) / bounds.height) * height,
      };
    }
    function move(event) {
      const point = position(event);
      if (!point) return;
      // Touch scrolling remains native unless a node was explicitly grabbed.
      if (event.pointerType === 'touch' && !drag) return;
      pointer = point;
      if (drag) {
        drag.x = point.x;
        drag.y = point.y;
      }
      wake();
    }
    function down(event) {
      if (event.button !== 0) return;
      const hit = event.target.closest('[data-letter-node]');
      const point = position(event);
      if (!hit || !point) return;
      const letter = Number(hit.dataset.letterIndex);
      const node = Number(hit.dataset.letterNode);
      const [x, y] = footerLetters[letter].nodes[node];
      drag = { letter, origin: { x, y }, ...point };
      svg.setPointerCapture?.(event.pointerId);
      event.preventDefault();
      wake();
    }
    function release() {
      drag = null;
      pointer = null;
      wake();
    }
    function leave() {
      if (!drag) release();
    }
    svg.addEventListener('pointermove', move);
    svg.addEventListener('pointerdown', down);
    svg.addEventListener('pointerup', release);
    svg.addEventListener('pointercancel', release);
    svg.addEventListener('lostpointercapture', release);
    svg.addEventListener('pointerleave', leave);
    return () => {
      window.cancelAnimationFrame(frame);
      svg.removeEventListener('pointermove', move);
      svg.removeEventListener('pointerdown', down);
      svg.removeEventListener('pointerup', release);
      svg.removeEventListener('pointercancel', release);
      svg.removeEventListener('lostpointercapture', release);
      svg.removeEventListener('pointerleave', leave);
      letters.forEach((letter) => {
        letter.points = letter.original.points.map((point) => ({ ...point }));
      });
      render();
    };
  }, [svgRef, enabled]);
}
