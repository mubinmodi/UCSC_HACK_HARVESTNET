import { describe, expect, it, vi } from 'vitest';
import { api, ApiError, API_BASE_URL, DEFAULT_API_BASE_URL, isExampleData, showablePickups, type Pickup } from '../api';
import { examples, HOUSEHOLD_OPERATIONS, mockApi, operationFor } from './contract';

const ex = (op: string) => examples[op].example.request;

/** Call each household operation with the contract example's own inputs. */
const callFor: Record<(typeof HOUSEHOLD_OPERATIONS)[number], () => Promise<unknown>> = {
  get_fair_share: () => api.getFairShare(Number(ex('get_fair_share').query!.household_size), 'en'),
  preview_request: () => api.previewRequest(ex('preview_request').body as never),
  create_request: () => api.createRequest(ex('create_request').body as never),
  list_food_banks: () => api.listFoodBanks(ex('list_food_banks').query!.neighborhood, ex('list_food_banks').query!.request_code),
  choose_food_banks: () => api.chooseFoodBanks('K7P4', (ex('choose_food_banks').body as { food_bank_ids: string[] }).food_bank_ids),
  get_request: () => api.getRequest('K7P4', 'en'),
  release_pickup: () => api.releasePickup('pk-1013-0001', 'K7P4'),
};

describe('API client matches the public API contract', () => {
  it('defaults to the live API skeleton', () => {
    expect(DEFAULT_API_BASE_URL).toBe('https://5ibpa6ukufm2dmyidprwzv5e7e0vrpfj.lambda-url.us-east-2.on.aws');
    expect(API_BASE_URL).toBe(DEFAULT_API_BASE_URL);
  });

  it.each(HOUSEHOLD_OPERATIONS)('%s sends the example method, path, query, and body, and returns the example', async operation => {
    const { calls } = mockApi();
    const result = await callFor[operation]();
    expect(calls).toHaveLength(1);
    const [call] = calls;
    const contract = examples[operation];
    expect(call.method).toBe(contract.method);
    expect(operationFor(call.method, call.url.pathname)?.operation).toBe(operation);
    expect(call.url.origin + call.url.pathname).toBe(API_BASE_URL + contract.example.request.path);
    expect(Object.fromEntries(call.url.searchParams)).toEqual(contract.example.request.query ?? {});
    expect(call.body).toEqual(contract.example.request.body);
    if (call.body !== undefined) expect(call.headers['Content-Type']).toBe('application/json');
    expect(result).toEqual(contract.example.response.body);
  });

  it('turns an API error body into an ApiError with status and code', async () => {
    mockApi(() => ({ status: 503, body: { error: { code: 'unavailable', message: 'Try again' } } }));
    const err = await api.getRequest('K7P4', 'en').catch(e => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ kind: 'http', status: 503, code: 'unavailable', message: 'Try again' });
  });

  it('reports a network failure as kind "network"', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))));
    await expect(api.getFairShare(4, 'en')).rejects.toMatchObject({ kind: 'network' });
  });

  it('reports a reply that is not JSON as kind "bad_response"', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('<html>oops</html>', { status: 200 })));
    await expect(api.getFairShare(4, 'en')).rejects.toMatchObject({ kind: 'bad_response' });
  });

  it('labels every skeleton reply as example data', () => {
    for (const operation of HOUSEHOLD_OPERATIONS) {
      expect(isExampleData(examples[operation].example.response.body as never)).toBe(true);
    }
    expect(isExampleData({ mode: 'live' })).toBe(false);
  });

  it('shows only committed, not-yet-collected pickups', () => {
    const base = (examples.get_request.example.response.body as { pickups: Pickup[] }).pickups[0];
    const pickups = ['committed', 'moving', 'at_food_bank', 'negotiating', 'held', 'offered', 'released', 'collected', 'unclaimed'].map(
      status => ({ ...base, pickup_id: status, status }),
    );
    expect(showablePickups(pickups).map(p => p.status)).toEqual(['committed', 'moving', 'at_food_bank']);
  });
});
