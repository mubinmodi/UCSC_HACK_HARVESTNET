/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Relative asset paths: the page works from the site root and from any folder.
  // deploy/aws/setup.sh builds this app with --base=/ because it is served at "/".
  base: './',
  // Older phone browsers: keep the output syntax conservative.
  build: { target: 'es2020' },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    unstubGlobals: true,
  },
});
