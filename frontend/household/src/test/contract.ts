// Loads the agreed public API examples (docs/contracts/examples/public-api/*.json) and builds a
// fetch mock that answers like the API skeleton does. No network is used in tests.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { vi } from 'vitest';
import { API_BASE_URL } from '../api';

export interface Example {
  operation: string;
  method: string;
  path: string;
  example: {
    request: { path: string; query?: Record<string, string>; body?: unknown };
    response: { status: number; body: Record<string, unknown> };
  };
}

const here = dirname(fileURLToPath(import.meta.url));
export const EXAMPLES_DIR = resolve(here, '../../../../docs/contracts/examples/public-api');

export const examples: Record<string, Example> = Object.fromEntries(
  readdirSync(EXAMPLES_DIR)
    .filter(f => f.endsWith('.json'))
    .map(f => {
      const data = JSON.parse(readFileSync(join(EXAMPLES_DIR, f), 'utf8')) as Example;
      return [data.operation, data];
    }),
);

export const HOUSEHOLD_OPERATIONS = [
  'get_fair_share',
  'preview_request',
  'create_request',
  'list_food_banks',
  'choose_food_banks',
  'get_request',
  'release_pickup',
] as const;

export interface RecordedCall {
  method: string;
  url: URL;
  body: unknown;
  headers: Record<string, string>;
}

function matches(template: string, path: string): boolean {
  const a = template.split('/').filter(Boolean);
  const b = path.split('/').filter(Boolean);
  return a.length === b.length && a.every((seg, i) => (seg.startsWith('{') && seg.endsWith('}')) || seg === b[i]);
}

/** Find the contract operation for a method and path, the way the skeleton routes it. */
export function operationFor(method: string, path: string): Example | undefined {
  const candidates = Object.values(examples).filter(e => e.method === method && matches(e.path, path));
  // Prefer the route with the most literal segments (as the skeleton does).
  const literals = (e: Example) => e.path.split('/').filter(seg => seg && !seg.startsWith('{')).length;
  return candidates.sort((x, y) => literals(y) - literals(x))[0];
}

export type Override = (op: string, call: RecordedCall) => { status: number; body: unknown } | undefined;

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

/** Install a fetch mock that answers every call with its contract example. */
export function mockApi(override?: Override) {
  const calls: RecordedCall[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = (init?.method ?? 'GET').toUpperCase();
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
    const headers = Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>));
    const call: RecordedCall = { method, url, body, headers };
    calls.push(call);
    if (`${url.origin}` !== new URL(API_BASE_URL).origin) {
      return new Response(JSON.stringify({ error: { code: 'not_found', message: 'wrong host' } }), { status: 404 });
    }
    const op = operationFor(method, url.pathname);
    const custom = op ? override?.(op.operation, call) : undefined;
    if (custom) return new Response(JSON.stringify(custom.body), { status: custom.status, headers: { 'Content-Type': 'application/json' } });
    if (!op) {
      return new Response(JSON.stringify({ mode: 'example', error: { code: 'not_found', message: 'No such route' } }), { status: 404 });
    }
    return new Response(JSON.stringify(clone(op.example.response.body)), {
      status: op.example.response.status,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls, fetchMock };
}
