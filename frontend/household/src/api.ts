// Household client for the HarvestNet public API (docs/contracts/public-api.md, "Households").
//
// Every request and response shape here follows the agreed contract and its examples in
// docs/contracts/examples/public-api/. The page never calculates a fair share, a balance, or
// a portion: every number it shows comes from these responses (ADR-0002).
//
// The gateway serves the page and the API on one origin, so without VITE_API_BASE_URL the page
// calls `/api` on its own origin. Set VITE_API_BASE_URL for another address. The example API
// skeleton, which answers every call with the contract's synthetic example ("mode": "example"),
// is an explicit dev option: VITE_API_BASE_URL=<SKELETON_API_BASE_URL>.

export const DEFAULT_API_BASE_URL = '/api';
export const SKELETON_API_BASE_URL = 'https://5ibpa6ukufm2dmyidprwzv5e7e0vrpfj.lambda-url.us-east-2.on.aws';

/** The configured address without trailing slashes, or the same-origin default. */
export function resolveApiBase(configured: string | undefined): string {
  return (configured?.trim() || DEFAULT_API_BASE_URL).replace(/\/+$/, '');
}

export const API_BASE_URL = resolveApiBase(import.meta.env.VITE_API_BASE_URL as string | undefined);

/** Slow connections get a generous wait before we give up and offer "Try again". */
export const REQUEST_TIMEOUT_MS = 20_000;

export type Language = 'en' | 'es';
export type Weekday = 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun';
/** "not_said" covers "Prefer not to say" and an unanswered question (front_desk.SnapAnswer). */
export type SnapAnswer = 'yes' | 'no' | 'not_said';
/** "example" from the skeleton; "live", "replay", or "synthetic" from real logic. */
export type Mode = 'example' | 'live' | 'replay' | 'synthetic' | (string & {});

/** A household's weekly pickup window: days plus local clock times ("18:00"), open ends are null. */
export interface PickupWindowPreference {
  days: Weekday[];
  start: string | null;
  end: string | null;
}

/** The household's answers, as preview_request and create_request take them. */
export interface HouseholdAnswers {
  language: Language;
  household_size: number;
  pickup_windows: PickupWindowPreference[];
  limited_fridge: boolean;
  neighborhood: string;
  cant_eat: string[];
  snap: SnapAnswer;
}

export interface CreateRequestBody extends HouseholdAnswers {
  channel: 'web';
  consent: true;
  /** Optional, for pickup emails only. Write-only: the API never returns it. */
  email?: string;
}

interface Labeled {
  mode: Mode;
  synthetic?: boolean;
}

export interface FairShare extends Labeled {
  household_size: number;
  fair_share_lb: number;
  period: string;
  table_version: string;
  is_placeholder?: boolean;
  wording: string;
}

export interface DraftRequest extends Partial<HouseholdAnswers> {
  missing: string[];
  dropped: unknown[];
}

export interface Preview extends Labeled {
  saved: false;
  draft_request: DraftRequest;
  complete: boolean;
  fair_share_lb: number | null;
  read_back: string;
  missing_questions: string[];
  consent_question: string | null;
}

export interface CreatedRequest extends Labeled {
  request_code: string;
  household_size: number;
  fair_share_lb: number;
  received_this_week_lb: number;
  table_version: string;
  chosen_food_bank_ids: string[];
  emails: boolean;
  expires_at: string;
  next: string;
}

export interface TimeWindow {
  start: string;
  end: string;
}

export interface CommittedProduce {
  produce_id: string;
  name: string;
  pounds: number;
  badges: string[];
}

export interface FoodBank {
  food_bank_id: string;
  name: string;
  area: string;
  pickup_windows: TimeWindow[];
  fits_your_pickup_times: boolean;
  committed_now: CommittedProduce[];
}

export interface FoodBankList extends Labeled {
  food_banks: FoodBank[];
}

export interface ChosenFoodBanks extends Labeled {
  request_code: string;
  chosen_food_bank_ids: string[];
  status: string;
  message: string;
}

export interface PickupItem {
  produce_id: string;
  name: string;
  pounds: number;
}

export interface Pickup {
  pickup_id: string;
  food_bank_id: string;
  food_bank_name: string;
  window: TimeWindow;
  items: PickupItem[];
  pounds: number;
  lot_id: string;
  version: number;
  status: string;
  wording: string;
}

export interface RequestStatus extends Labeled {
  request_code: string;
  household_size: number;
  fair_share_lb: number;
  received_this_week_lb: number;
  chosen_food_bank_ids: string[];
  expires_at: string;
  pickups: Pickup[];
  market_match_tip: string | null;
}

export interface Release extends Labeled {
  pickup_id: string;
  status: string;
  released: boolean;
  released_lb: number;
  message: string;
}

/**
 * Pickup statuses a household may see: committed and not yet collected. Anything still being
 * negotiated (or released, collected, unclaimed) is never shown (MVP_DESIGN.md Workflow 1,
 * front_desk.REPORTABLE_STATUSES).
 */
export const SHOWABLE_PICKUP_STATUSES: ReadonlySet<string> = new Set(['committed', 'moving', 'at_food_bank']);

export function showablePickups(pickups: readonly Pickup[]): Pickup[] {
  return pickups.filter(p => SHOWABLE_PICKUP_STATUSES.has(p.status));
}

/** True when a response is example or synthetic data, so the page must say so. */
export function isExampleData(body: Labeled | null | undefined): boolean {
  return !!body && (body.mode === 'example' || body.mode === 'synthetic' || body.synthetic === true);
}

export type ApiErrorKind = 'network' | 'timeout' | 'http' | 'bad_response';

/** Any failed call. `code` and `message` come from the API's `{"error": {...}}` body when present. */
export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string | null;

  constructor(kind: ApiErrorKind, message: string, status: number | null = null, code: string | null = null) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
    this.code = code;
  }
}

type Query = Record<string, string>;

async function call<T>(method: 'GET' | 'POST' | 'PUT', path: string, options: { query?: Query; body?: unknown } = {}): Promise<T> {
  const qs = options.query ? `?${new URLSearchParams(options.query).toString()}` : '';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const init: RequestInit = { method, headers: { Accept: 'application/json' }, cache: 'no-store', signal: controller.signal };
  if (options.body !== undefined) {
    init.headers = { ...init.headers, 'Content-Type': 'application/json' };
    init.body = JSON.stringify(options.body);
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}${qs}`, init);
  } catch (err) {
    clearTimeout(timer);
    if (controller.signal.aborted) throw new ApiError('timeout', 'The request took too long.');
    throw new ApiError('network', err instanceof Error ? err.message : 'Network error');
  }
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    data = undefined;
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) {
    const error = (data as { error?: { code?: unknown; message?: unknown } } | undefined)?.error;
    throw new ApiError(
      'http',
      typeof error?.message === 'string' ? error.message : `HTTP ${response.status}`,
      response.status,
      typeof error?.code === 'string' ? error.code : null,
    );
  }
  if (data === undefined || data === null || typeof data !== 'object') {
    throw new ApiError('bad_response', 'The API sent a reply the page could not read.', response.status);
  }
  return data as T;
}

const seg = (value: string) => encodeURIComponent(value);

export const api = {
  /** GET /fair-share?household_size=4&language=en */
  getFairShare(householdSize: number, language: Language) {
    return call<FairShare>('GET', '/fair-share', { query: { household_size: String(householdSize), language } });
  },
  /** POST /requests/preview. Saves nothing. */
  previewRequest(answers: HouseholdAnswers) {
    return call<Preview>('POST', '/requests/preview', { body: answers });
  },
  /** POST /requests, only after the household says yes to the consent question. */
  createRequest(body: CreateRequestBody) {
    return call<CreatedRequest>('POST', '/requests', { body });
  },
  /** GET /food-banks?neighborhood=Watsonville&request_code=K7P4 */
  listFoodBanks(neighborhood: string, requestCode: string) {
    return call<FoodBankList>('GET', '/food-banks', { query: { neighborhood, request_code: requestCode } });
  },
  /** PUT /requests/{request_code}/food-banks */
  chooseFoodBanks(requestCode: string, foodBankIds: string[]) {
    return call<ChosenFoodBanks>('PUT', `/requests/${seg(requestCode)}/food-banks`, { body: { food_bank_ids: foodBankIds } });
  },
  /** GET /requests/{request_code}?language=en */
  getRequest(requestCode: string, language: Language) {
    return call<RequestStatus>('GET', `/requests/${seg(requestCode)}`, { query: { language } });
  },
  /** POST /pickups/{pickup_id}/release: the "Can't make it" button. */
  releasePickup(pickupId: string, requestCode: string) {
    return call<Release>('POST', `/pickups/${seg(pickupId)}/release`, { body: { request_code: requestCode } });
  },
};
