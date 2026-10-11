import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import { resetSessionForTests } from '../session';

// jsdom has no layout; the app scrolls to the top when the page changes.
window.scrollTo = () => {};

afterEach(() => {
  cleanup();
  resetSessionForTests();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
