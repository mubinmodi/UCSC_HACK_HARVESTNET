// HarvestNet public API client (docs/contracts/public-api.md).
// Every call uses the contract's method, path, query, and body exactly. The API only reads
// and writes records; nothing here decides or commits anything for an organization.
import type {
  ApprovalInput,
  ApprovalList,
  ApprovalRecorded,
  ConditionCheckInput,
  ConditionCheckRecorded,
  CounterInput,
  CounterQueued,
  FoodBankDashboard,
  FoodBankList,
  FoodBankStatusInput,
  FoodBankStatusSaved,
  Lot,
  LotVersions,
  PickupConfirmed,
  PickupConfirmInput,
  ProduceProfiles,
  SurplusOfferCreated,
  SurplusOfferInput,
} from './types';
import { staffToken } from './session';

/** The gateway serves the pages and the API on one origin, so the default is `/api` on the page's own origin. */
export const DEFAULT_API_BASE_URL = '/api';

/** The example API skeleton on AWS, answering every operation with the contract's example. An explicit dev option: set VITE_API_BASE_URL to it. */
export const SKELETON_API_BASE_URL = 'https://5ibpa6ukufm2dmyidprwzv5e7e0vrpfj.lambda-url.us-east-2.on.aws';

/** The configured address without trailing slashes, or the same-origin default. */
export function resolveApiBase(configured: string | undefined): string {
  return (configured?.trim() || DEFAULT_API_BASE_URL).replace(/\/+$/, '');
}

export const API_BASE_URL: string = resolveApiBase(import.meta.env.VITE_API_BASE_URL as string | undefined);

/** A route's full address: an absolute base is used as is, a path like `/api` resolves against the page's origin. */
export function apiUrl(route: string, base: string = API_BASE_URL): URL {
  return new URL(base + route, window.location.origin);
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** A problem with what the user entered, caught before anything is sent. */
export class UserInputError extends Error {}

type Method = 'GET' | 'POST' | 'PUT';

interface CallOptions {
  query?: Record<string, string>;
  body?: unknown;
  /** The organization whose staff token goes in the Authorization header, if one is set. */
  staffFor?: string;
}

const path = (...parts: string[]) => '/' + parts.map(encodeURIComponent).join('/');

async function call<T>(method: Method, route: string, options: CallOptions = {}): Promise<T> {
  const url = apiUrl(route);
  for (const [key, value] of Object.entries(options.query ?? {})) url.searchParams.set(key, value);
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  const token = options.staffFor ? staffToken.get(options.staffFor) : '';
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: 'no-store',
    });
  } catch {
    throw new ApiError(0, 'network', 'Could not reach the HarvestNet API. Check your connection and try again.');
  }

  let data: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    const error = (data as { error?: { code?: string; message?: string } } | null)?.error;
    throw new ApiError(response.status, error?.code ?? 'http_error', error?.message ?? `The API answered ${response.status}.`);
  }
  return data as T;
}

export const api = {
  listProduceProfiles: () => call<ProduceProfiles>('GET', '/produce-profiles'),

  listFoodBanks: () => call<FoodBankList>('GET', '/food-banks'),

  createSurplusOffer: (offer: SurplusOfferInput) =>
    call<SurplusOfferCreated>('POST', '/surplus-offers', { body: offer, staffFor: offer.donor_id }),

  getLot: (lotId: string) => call<Lot>('GET', path('lots', lotId)),

  listLotVersions: (lotId: string) => call<LotVersions>('GET', path('lots', lotId, 'versions')),

  getFoodBankDashboard: (foodBankId: string) =>
    call<FoodBankDashboard>('GET', path('food-banks', foodBankId, 'dashboard'), { staffFor: foodBankId }),

  updateFoodBankStatus: (foodBankId: string, status: FoodBankStatusInput) =>
    call<FoodBankStatusSaved>('PUT', path('food-banks', foodBankId, 'status'), { body: status, staffFor: foodBankId }),

  submitCounter: (lotId: string, counter: CounterInput) =>
    call<CounterQueued>('POST', path('lots', lotId, 'counters'), { body: counter, staffFor: counter.organization_id }),

  confirmPickup: (confirmation: PickupConfirmInput) =>
    call<PickupConfirmed>('POST', '/pickup-confirmations', { body: confirmation, staffFor: confirmation.food_bank_id }),

  listApprovals: (organizationId: string) =>
    call<ApprovalList>('GET', '/approvals', { query: { organization_id: organizationId }, staffFor: organizationId }),

  recordApproval: (approval: ApprovalInput) =>
    call<ApprovalRecorded>('POST', '/approvals', { body: approval, staffFor: approval.organization_id }),

  /** Proposed core route (#9), not in the agreed contract; the skeleton answers 404. */
  submitConditionCheck: (lotId: string, check: ConditionCheckInput) =>
    call<ConditionCheckRecorded>('POST', path('lots', lotId, 'condition-checks'), { body: check, staffFor: check.organization_id }),
};

export type Api = typeof api;

/** A short explanation for an error, never including request headers or tokens. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Staff sign-in needed. Enter your organization’s staff token in Settings.';
    if (error.status === 409) return `${error.message} The plan changed since you loaded it. Refresh and review the newest version.`;
    if (error.status === 404) return `${error.message} (not found on this API).`;
    return error.message;
  }
  if (error instanceof UserInputError) return error.message;
  return 'Something went wrong. Please try again.';
}
