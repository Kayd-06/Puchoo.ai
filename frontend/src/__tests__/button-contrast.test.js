import { readFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import { resolve } from 'node:path';
import process from 'node:process';

const luminance = (hex) => {
  const rgb = hex.match(/[a-f\d]{2}/gi).map((c) => {
    const v = parseInt(c, 16) / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
};

it('keeps every button tone readable in both theme palettes', () => {
  const css = readFileSync(resolve(process.cwd(), 'src/styles/buttons.css'), 'utf8');
  for (const theme of ['dark', 'light']) {
    const block = css.match(new RegExp(`/\\* ${theme} palette \\*/([\\s\\S]*?)\\}`))[1];
    const tokens = Object.fromEntries(
      [...block.matchAll(/--control-([\w-]+):\s*(#[a-f\d]{6})/gi)].map((m) => [m[1], m[2]]),
    );
    for (const tone of ['secondary', 'hover', 'primary', 'primary-hover', 'danger', 'disabled']) {
      const values = [luminance(tokens[`${tone}-fg`]), luminance(tokens[`${tone}-bg`])].sort(
        (a, b) => a - b,
      );
      expect((values[1] + 0.05) / (values[0] + 0.05), `${theme} ${tone}`).toBeGreaterThanOrEqual(
        4.5,
      );
    }
  }
});
