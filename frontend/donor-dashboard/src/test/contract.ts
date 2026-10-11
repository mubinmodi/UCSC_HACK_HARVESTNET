// Test helpers: the contract's example files (docs/contracts/examples/public-api/), and a
// fetch mock that answers each operation with its example response. No network is used.
import { vi } from 'vitest';

export interface ContractExample {
  operation: string;
  method: 'GET' | 'POST' | 'PUT';
  path: string;
  example: {
    request: { path: string; query?: Record<string, string>; body?: unknown };
    response: { status: number; body: unknown };
  };
}

const files = import.meta.glob<ContractExample>('../../../../docs/contracts/examples/public-api/*.json', { eager: true, import: 'default' });

export const examples: Record<string, ContractExample> = Object.fromEntries(
  Object.values(files).map((file) => [file.operation, file]),
);

export function example(operation: string): ContractExample {
  const found = examples[operation];
  if (!found) throw new Error(`No contract example for ${operation}`);
  return found;
}

export const exampleBody = <T,>(operation: string): T => structuredClone(example(operation).example.response.body) as T;

/** Turn a contract path template ("/lots/{lot_id}") into a matcher. */
function matcher(template: string) {
  return new RegExp('^' + template.replace(/\{[^}]+\}/g, '[^/]+') + '$');
}

export interface Recorded {
  method: string;
  url: URL;
  body: unknown;
  headers: Record<string, string>;
}

type Override = (call: Recorded) => { status: number; body: unknown } | undefined;

/**
 * Mock fetch: each request is matched to a contract operation by method and path template
 * and answered with that operation's example response, unless an override answers first.
 */
export function mockApi(overrides: Record<string, unknown | Override> = {}) {
  const calls: Recorded[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = (init?.method ?? 'GET').toUpperCase();
    const headers = Object.fromEntries(Object.entries((init?.headers as Record<string, string>) ?? {}).map(([k, v]) => [k.toLowerCase(), v]));
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    const call = { method, url, body, headers };
    calls.push(call);
    const op = Object.values(examples).find((e) => e.method === method && matcher(e.path).test(url.pathname));
    let status = 404;
    let payload: unknown = { error: { code: 'not_found', message: 'Unknown operation' } };
    if (op) {
      status = op.example.response.status;
      payload = structuredClone(op.example.response.body);
      const override = overrides[op.operation];
      if (typeof override === 'function') {
        const answer = (override as Override)(call);
        if (answer) ({ status, body: payload } = answer);
      } else if (override !== undefined) {
        payload = structuredClone(override);
      }
    } else {
      const extra = overrides[`${method} ${url.pathname}`];
      if (typeof extra === 'function') {
        const answer = (extra as Override)(call);
        if (answer) ({ status, body: payload } = answer);
      }
    }
    return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, calls };
}
