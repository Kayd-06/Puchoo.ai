import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { backendTarget } from '../scripts/dev-config.mjs';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
  },
  server: {
    proxy: {
      '/api': {
        target: backendTarget(),
        changeOrigin: true,
      },
    },
  },
});
