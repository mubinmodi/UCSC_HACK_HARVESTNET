/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Older phone browsers: keep the output syntax conservative.
  build: { target: 'es2020' },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // Tests call an absolute address so the fetch mock can tell the API's host from any other.
    env: { VITE_API_BASE_URL: 'https://api.harvestnet.test' },
    restoreMocks: true,
    unstubGlobals: true,
  },
});
