import { useEffect, useRef } from 'react';
import { useReducedMotion } from 'framer-motion';

function buildDots(count) {
  const dots = [];
  for (let index = 0; index < count; index += 1) {
    const phi = Math.acos(1 - (2 * (index + 0.5)) / count);
    const theta = Math.PI * (1 + Math.sqrt(5)) * index;
    dots.push([Math.sin(phi) * Math.cos(theta), Math.cos(phi), Math.sin(phi) * Math.sin(theta)]);
  }
  return dots;
}

const DOTS = buildDots(520);
const RINGS = [
  { radius: 0.72, tilt: 0.2, squash: 0.28 },
  { radius: 0.84, tilt: 0.9, squash: 0.22 },
  { radius: 0.62, tilt: 1.5, squash: 0.4 },
  { radius: 0.9, tilt: 2.2, squash: 0.18 },
  { radius: 0.5, tilt: 0.6, squash: 0.55 },
  { radius: 0.76, tilt: 2.8, squash: 0.32 },
];

export default function NodeSphere({ className = 'h-full w-full' }) {
  const canvasRef = useRef(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const context = canvas.getContext('2d');
    let frame = 0;
    const started = performance.now();

    function paint(now) {
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      if (
        canvas.width !== Math.floor(width * ratio) ||
        canvas.height !== Math.floor(height * ratio)
      ) {
        canvas.width = Math.floor(width * ratio);
        canvas.height = Math.floor(height * ratio);
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      const time = reduce ? 0.6 : (now - started) / 1000;
      const rotation = time * 0.28;
      const centerX = width / 2;
      const centerY = height / 2;
      const scale = Math.min(width, height) * 0.36;

      DOTS.forEach(([x, y, z]) => {
        const xr = x * Math.cos(rotation) + z * Math.sin(rotation);
        const zr = -x * Math.sin(rotation) + z * Math.cos(rotation);
        const depth = (zr + 1) / 2;
        context.globalAlpha = 0.18 + depth * 0.8;
        context.fillStyle = '#e8eefc';
        context.beginPath();
        context.arc(centerX + xr * scale, centerY + y * scale, 0.8 + depth * 1.3, 0, Math.PI * 2);
        context.fill();
      });

      context.lineWidth = 1.15;
      context.strokeStyle = 'rgba(255,255,255,0.82)';
      RINGS.forEach((ring) => {
        context.beginPath();
        const steps = 90;
        for (let step = 0; step <= steps; step += 1) {
          const angle = (step / steps) * Math.PI * 2 + time * 0.12;
          const x = Math.cos(angle) * ring.radius;
          const y0 = Math.sin(angle) * ring.radius * ring.squash;
          const z0 = Math.sin(angle) * ring.radius;
          const y = y0 * Math.cos(ring.tilt) - z0 * Math.sin(ring.tilt);
          const z = y0 * Math.sin(ring.tilt) + z0 * Math.cos(ring.tilt);
          const xr = x * Math.cos(rotation) + z * Math.sin(rotation);
          const px = centerX + xr * scale;
          const py = centerY + y * scale;
          if (step === 0) context.moveTo(px, py);
          else context.lineTo(px, py);
        }
        context.globalAlpha = 0.72;
        context.stroke();
      });
      context.globalAlpha = 1;
      if (!reduce) frame = requestAnimationFrame(paint);
    }

    frame = requestAnimationFrame(paint);
    return () => cancelAnimationFrame(frame);
  }, [reduce]);

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />;
}
