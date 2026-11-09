// Engineering ceilings, not a measured phone-performance guarantee.
export function universePolicy({
  width,
  height,
  dpr = 1,
  reducedMotion = false,
  hidden = false,
  hardwareConcurrency,
  deviceMemory,
  saveData = false,
}) {
  if (
    reducedMotion ||
    hidden ||
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0 ||
    width > 16384 ||
    height > 16384
  )
    return { mode: 'off' };
  const constrained =
    saveData ||
    (hardwareConcurrency > 0 && hardwareConcurrency <= 2) ||
    (deviceMemory > 0 && deviceMemory <= 2);
  const compact = width < 720;
  const mode = constrained ? 'static' : 'animated';
  const maxPixels = constrained ? 500000 : 1500000;
  const ratio = Math.min(
    Number.isFinite(dpr) && dpr > 0 ? dpr : 1,
    1.5,
    4096 / width,
    4096 / height,
    Math.sqrt(maxPixels / (width * height)),
  );
  const count = constrained ? 240 : compact ? 900 : 2400;
  const clusters = constrained ? 2 : 8;
  const dust = Math.floor((count - clusters) * 0.3),
    still = Math.floor((count - clusters) * 0.45);
  return {
    mode,
    ratio,
    pixelWidth: Math.max(1, Math.floor(width * ratio)),
    pixelHeight: Math.max(1, Math.floor(height * ratio)),
    fps: compact ? 18 : 24,
    clusters,
    dust,
    still,
    streams: count - clusters - dust - still,
  };
}
