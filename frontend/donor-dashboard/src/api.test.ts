// Each API call this app makes must match the agreed contract: the example's method,
// path, query, and body, and it must hand back the example's response unchanged.
import { describe, expect, it } from 'vitest';
import { api, API_BASE_URL, ApiError, DEFAULT_API_BASE_URL, describeError } from './api';
import { staffToken } from './session';
import { example, examples, mockApi } from './test/contract';
import type {
  ApprovalInput,
  CounterInput,
  FoodBankStatusInput,
  PickupConfirmInput,
  SurplusOfferInput,
} from './types';

// `householdQuery`: list_food_banks' query filters (neighborhood, request_code) are for
// household pages. Staff screens call it without them, which the core accepts.
type Case = { operation: string; run: () => Promise<unknown>; householdQuery?: boolean };

const req = (operation: string) => example(operation).example.request;
const segment = (operation: string, index: number) => req(operation).path.split('/')[index];

const cases: Case[] = [
  { operation: 'list_produce_profiles', run: () => api.listProduceProfiles() },
  { operation: 'list_food_banks', run: () => api.listFoodBanks(), householdQuery: true },
  { operation: 'create_surplus_offer', run: () => api.createSurplusOffer(req('create_surplus_offer').body as SurplusOfferInput) },
  { operation: 'get_lot', run: () => api.getLot(segment('get_lot', 2)) },
  { operation: 'list_lot_versions', run: () => api.listLotVersions(segment('list_lot_versions', 2)) },
  { operation: 'get_food_bank_dashboard', run: () => api.getFoodBankDashboard(segment('get_food_bank_dashboard', 2)) },
  {
    operation: 'update_food_bank_status',
    run: () => api.updateFoodBankStatus(segment('update_food_bank_status', 2), req('update_food_bank_status').body as FoodBankStatusInput),
  },
  { operation: 'submit_counter', run: () => api.submitCounter(segment('submit_counter', 2), req('submit_counter').body as CounterInput) },
  { operation: 'confirm_pickup', run: () => api.confirmPickup(req('confirm_pickup').body as PickupConfirmInput) },
  { operation: 'list_approvals', run: () => api.listApprovals(req('list_approvals').query!.organization_id) },
  { operation: 'record_approval', run: () => api.recordApproval(req('record_approval').body as ApprovalInput) },
];

describe('API calls match the public API contract', () => {
  it('defaults to the live API skeleton', () => {
    expect(DEFAULT_API_BASE_URL).toBe('https://5ibpa6ukufm2dmyidprwzv5e7e0vrpfj.lambda-url.us-east-2.on.aws');
    expect(API_BASE_URL).toBe(DEFAULT_API_BASE_URL);
  });

  it('covers every operation the donor page and dashboard use', () => {
    for (const { operation } of cases) expect(examples[operation], operation).toBeDefined();
  });

  it.each(cases)('$operation uses the contract method, path, query and body', async ({ operation, run, householdQuery }) => {
    const { calls } = mockApi();
    const contract = example(operation);
    const result = await run();
    expect(calls).toHaveLength(1);
    const [call] = calls;
    expect(call.method).toBe(contract.method);
    expect(call.url.origin + call.url.pathname).toBe(API_BASE_URL + contract.example.request.path);
    expect(Object.fromEntries(call.url.searchParams)).toEqual(householdQuery ? {} : (contract.example.request.query ?? {}));
    expect(call.body).toEqual(contract.example.request.body);
    if (contract.example.request.body !== undefined) expect(call.headers['content-type']).toBe('application/json');
    expect(result).toEqual(contract.example.response.body);
  });

  it('sends the proposed condition check to the core route', async () => {
    const { calls } = mockApi({
      'POST /lots/lot-market-1013/condition-checks': () => ({
        status: 200,
        body: { mode: 'synthetic', synthetic: true, lot_id: 'lot-market-1013', version: 4, status: 'condition_recorded', committed: false },
      }),
    });
    const body = {
      organization_id: 'city',
      version: 3,
      produce_id: 'romaine',
      condition_grade: 'use_soon' as const,
      usable_until: '2026-10-13T23:59:00-07:00',
      reason: 'Checked on arrival.',
    };
    const result = await api.submitConditionCheck('lot-market-1013', body);
    expect(calls[0].method).toBe('POST');
    expect(calls[0].body).toEqual(body);
    expect(result.committed).toBe(false);
  });
});

describe('staff tokens', () => {
  it('attach only the organization’s own token, only to staff operations', async () => {
    staffToken.set('city', 'synthetic-city-staff');
    const { calls } = mockApi();
    await api.getFoodBankDashboard('city');
    await api.getLot('lot-market-1013');
    await api.getFoodBankDashboard('rural');
    expect(calls[0].headers.authorization).toBe('Bearer synthetic-city-staff');
    expect(calls[1].headers.authorization).toBeUndefined();
    expect(calls[2].headers.authorization).toBeUndefined();
    expect(calls[0].url.toString()).not.toContain('synthetic-city-staff');
  });

  it('live in sessionStorage, never localStorage', () => {
    staffToken.set('market', 'synthetic-market-staff');
    expect(window.sessionStorage.getItem('harvestnet.staff-token.market')).toBe('synthetic-market-staff');
    expect(Object.values({ ...window.localStorage })).not.toContain('synthetic-market-staff');
    staffToken.clear('market');
    expect(staffToken.get('market')).toBe('');
  });

  it('are not repeated in error messages', async () => {
    staffToken.set('city', 'synthetic-city-staff');
    mockApi({ get_food_bank_dashboard: () => ({ status: 401, body: { error: { code: 'unauthorized', message: 'organization staff authentication required' } } }) });
    const error = await api.getFoodBankDashboard('city').catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(describeError(error)).toMatch(/Staff sign-in needed/);
    expect(describeError(error)).not.toContain('synthetic-city-staff');
  });
});

describe('errors', () => {
  it('reads the contract error shape', async () => {
    mockApi({ record_approval: () => ({ status: 409, body: { error: { code: 'conflict', message: 'stale version' } } }) });
    const error = await api.recordApproval(req('record_approval').body as ApprovalInput).catch((e) => e);
    expect(error).toMatchObject({ status: 409, code: 'conflict' });
    expect(describeError(error)).toContain('Refresh and review the newest version');
  });
});
