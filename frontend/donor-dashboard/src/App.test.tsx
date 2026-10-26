// Screen tests. fetch is mocked with the contract's example responses; no network is used.
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import App from './App';
import { sessionValue, staffToken } from './session';
import { statusLabel } from './format';
import { example, exampleBody, mockApi } from './test/contract';
import coolerBoard from './test/fixtures/dashboard-cooler-failure.json';
import type { ApprovalList, FoodBankDashboard, Lot } from './types';

function openPage(page: string) {
  sessionValue.set('page', page);
  return render(<App />);
}

const nav = () => screen.getByRole('navigation', { name: 'Main' });

describe('donor page', () => {
  it('builds the produce list from GET /produce-profiles and sends the contract offer shape', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi();
    openPage('report');

    const produce = await screen.findByLabelText('Produce');
    const names = within(produce).getAllByRole('option').map((o) => o.textContent);
    expect(names).toEqual(['Apples', 'Romaine lettuce', 'Potatoes', 'Tomatoes']);

    await user.type(screen.getByLabelText('Quantity'), '300');
    await user.click(screen.getByRole('button', { name: 'Add another item' }));
    const produceSelects = screen.getAllByLabelText('Produce');
    await user.selectOptions(produceSelects[1], 'potatoes');
    await user.type(screen.getAllByLabelText('Quantity')[1], '8');
    await user.selectOptions(screen.getAllByLabelText('Unit')[1], 'sack');
    await user.type(screen.getByLabelText('Pounds in each sack'), '50');
    await user.click(screen.getAllByRole('button', { name: /Use soon/ })[1]);
    await user.type(screen.getByLabelText('Must be gone by'), '2026-10-13T15:00');
    await user.click(screen.getByRole('button', { name: 'Offer this surplus' }));

    expect(await screen.findByText(/Your surplus is offered to nearby food banks/)).toBeInTheDocument();
    const post = calls.find((c) => c.method === 'POST' && c.url.pathname === '/surplus-offers')!;
    expect(post.body).toMatchObject({
      donor_id: 'market',
      recall_notice: false,
      items: [
        { produce_id: 'apples', quantity: 300, unit: 'lb', condition_grade: 'good' },
        { produce_id: 'potatoes', quantity: 8, unit: 'sack', lb_per_unit: 50, condition_grade: 'use_soon' },
      ],
      drop_off: { can_drop_off: false },
    });
    expect((post.body as { deadline: string }).deadline).toMatch(/^2026-10-13T15:00:00[+-]\d\d:\d\d$/);
    expect(screen.getByText(/Lot lot-market-1013, version 1/)).toBeInTheDocument();
    expect(screen.getAllByText(/Example response from the API skeleton/).length).toBeGreaterThan(0);
  });

  it('sends drop-off details with food banks named by the API', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi();
    openPage('report');
    await user.type(await screen.findByLabelText('Quantity'), '10');
    await user.type(screen.getByLabelText('Must be gone by'), '2026-10-13T15:00');
    await user.click(screen.getByRole('button', { name: /Yes I can drop off/ }));
    await user.type(screen.getByLabelText('Earliest drop-off'), '2026-10-13T13:00');
    await user.type(screen.getByLabelText('Latest drop-off'), '2026-10-13T15:00');
    await user.type(screen.getByLabelText('Vehicle can carry (lb)'), '700');
    const first = exampleBody<{ food_banks: { food_bank_id: string; name: string }[] }>('list_food_banks').food_banks[0];
    await user.click(await screen.findByLabelText(first.name));
    await user.click(screen.getByRole('button', { name: 'Offer this surplus' }));
    await screen.findByText(/Your surplus is offered/);
    const post = calls.find((c) => c.url.pathname === '/surplus-offers')!;
    expect((post.body as { drop_off: unknown }).drop_off).toMatchObject({ can_drop_off: true, refrigerated: false, capacity_lb: 700, food_bank_ids: [first.food_bank_id] });
  });

  it('never offers a lot with a recall notice', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi();
    openPage('report');
    await screen.findByLabelText('Produce');
    const recall = screen.getByRole('group', { name: /recall notice/ });
    await user.click(within(recall).getByRole('button', { name: 'Yes' }));
    expect(screen.getByRole('button', { name: 'Offer this surplus' })).toBeDisabled();
    expect(screen.getByText('Recalled produce is never offered.')).toBeInTheDocument();
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
  });

  it('shows each item’s status, who moves it, and every version with who proposed what and why', async () => {
    mockApi();
    const lot = exampleBody<Lot>('get_lot');
    openPage('lots');
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Lot ID'), lot.lot_id);
    await user.click(screen.getByRole('button', { name: 'Show' }));

    expect(await screen.findByText('Apples · 300 lb')).toBeInTheDocument();
    expect(screen.getByText('250 lb to Rural food bank · Donor drops off')).toBeInTheDocument();
    expect(screen.getByText('200 lb to City food bank · Food bank collects')).toBeInTheDocument();
    expect(screen.getAllByText('Households reached: 0')).toHaveLength(3);
    expect(screen.getByText(/Still waiting for:/).parentElement).toHaveTextContent('City food bank, Rural food bank, Eastside food bank');

    expect(await screen.findByText('Version 2')).toBeInTheDocument();
    expect(screen.getByText(/advocate · Counter/)).toBeInTheDocument();
    expect(screen.getByText(/Rural food bank's 42 households are furthest below fair share/)).toBeInTheDocument();
    expect(screen.getByText('Set Apples for Rural food bank to 250 lb.')).toBeInTheDocument();
  });
});

describe('lot and item status words', () => {
  it('shows plain labels for each item and the lot, never the raw status codes', async () => {
    const lot = exampleBody<Lot>('get_lot');
    lot.status = 'awaiting_approvals';
    lot.items[0].status = 'at_food_bank';
    lot.items[1].status = 'moving';
    lot.items[2].status = 'preserved_disagreement';
    mockApi({ get_lot: lot });
    openPage('lots');
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Lot ID'), lot.lot_id);
    await user.click(screen.getByRole('button', { name: 'Show' }));
    await screen.findByText('Apples · 300 lb');
    expect(screen.getByText('At the food bank')).toBeInTheDocument();
    expect(screen.getByText('On its way')).toBeInTheDocument();
    expect(screen.getByText('Disagreement kept')).toBeInTheDocument();
    expect(screen.getByText('Waiting for approvals')).toBeInTheDocument();
    for (const code of ['at_food_bank', 'awaiting_approvals', 'preserved_disagreement']) {
      expect(screen.queryByText(code)).not.toBeInTheDocument();
    }
  });

  it('shows unclaimed pounds with the reason, and how many households an item reached', async () => {
    const lot = exampleBody<Lot>('get_lot');
    lot.status = 'unclaimed';
    lot.items[0] = { ...lot.items[0], status: 'unclaimed', unclaimed_lb: 40, unclaimed_reason: 'Deadline passed without every exact-version approval; nothing auto-committed' };
    lot.items[1] = { ...lot.items[1], status: 'collected', households_reached: 7 };
    mockApi({ get_lot: lot });
    openPage('lots');
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Lot ID'), lot.lot_id);
    await user.click(screen.getByRole('button', { name: 'Show' }));
    await screen.findByText('Apples · 300 lb');
    expect(screen.getByText(/40 lb unclaimed: Deadline passed without every exact-version approval/)).toBeInTheDocument();
    expect(screen.getByText('Collected by households')).toBeInTheDocument();
    expect(screen.getByText('Households reached: 7')).toBeInTheDocument();
  });

  it('says what an item that is held, committed or unclaimed means', () => {
    expect(statusLabel('held')).toBe('Held, waiting for approvals');
    expect(statusLabel('committed')).toBe('Agreed and committed');
    expect(statusLabel('unclaimed')).toBe('Unclaimed');
    expect(statusLabel('something_new')).toBe('Something new');
  });
});

describe('lot status without per-item split', () => {
  it('reads destinations and movers from the current draft', async () => {
    const lot = exampleBody<Lot>('get_lot');
    for (const item of lot.items) delete item.split;
    mockApi({ get_lot: lot });
    sessionValue.set('page', 'lots');
    render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Lot ID'), lot.lot_id);
    await user.click(screen.getByRole('button', { name: 'Show' }));
    expect(await screen.findByText('250 lb to Rural food bank · Donor drops off')).toBeInTheDocument();
    expect(screen.getByText('200 lb to City food bank · Food bank collects')).toBeInTheDocument();
  });
});

describe('food bank dashboard', () => {
  it('shows capacity, counts-only fair-share gap, offers with the agent’s reason, and arrivals', async () => {
    mockApi();
    openPage('dashboard');
    expect(await screen.findByRole('heading', { name: 'City food bank', level: 1 })).toBeInTheDocument();
    const capacity = screen.getByRole('heading', { name: /Today’s capacity/ }).closest('section')!;
    expect(capacity).toHaveTextContent('250 lb cold · 200 lb dry');
    expect(capacity).toHaveTextContent('250 lb · refrigerated');
    expect(capacity).toHaveTextContent('Working · 4 °C');
    expect(screen.getByText(/Reading from beeceptor \(synthetic\)/)).toBeInTheDocument();
    const gap = screen.getByRole('heading', { name: /Fair-share gap/ }).closest('section')!;
    expect(within(gap).getByText('households below fair share').nextSibling).toHaveTextContent('3');
    expect(within(gap).getByText('people in them').nextSibling).toHaveTextContent('6');
    expect(within(gap).getByText('lb below fair share this week').nextSibling).toHaveTextContent('19');
    expect(screen.getByText(/At arrival \(2:20 pm\) we have 250 lb of cold space free/)).toBeInTheDocument();
    expect(screen.getByText(/From Farmers market · lot lot-market-1013, version 3/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Expected arrivals/ }).closest('section')).toHaveTextContent('Awaiting approvals');
  });

  it('never approves on its own: Accept needs a click and a confirmation of the exact version', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi();
    openPage('dashboard');
    await user.click(await screen.findByRole('button', { name: 'Approve version 3' }));
    expect(calls.some((c) => c.method === 'POST' && c.url.pathname === '/approvals')).toBe(false);

    const dialog = screen.getByRole('dialog', { name: 'Approve version 3?' });
    expect(within(dialog).getByText(/City food bank collects 200 lb romaine lettuce/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Yes, approve version 3' }));

    expect(await screen.findByText(/You approved version 3/)).toBeInTheDocument();
    expect(screen.getByText(/Not committed yet/)).toBeInTheDocument();
    const post = calls.find((c) => c.method === 'POST' && c.url.pathname === '/approvals')!;
    const approval = exampleBody<ApprovalList>('list_approvals').approvals[0];
    expect(post.body).toMatchObject({ lot_id: 'lot-market-1013', version: 3, organization_id: 'city', terms_hash: approval.terms_hash, decision: 'approve' });
    expect((post.body as { receipt_id: string }).receipt_id).toMatch(/^rcpt-/);
  });

  it('declines an exact version', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi();
    openPage('dashboard');
    await user.click(await screen.findByRole('button', { name: 'Decline' }));
    await user.click(screen.getByRole('button', { name: 'Yes, decline version 3' }));
    await screen.findByText(/You .* version 3/);
    expect(calls.find((c) => c.method === 'POST' && c.url.pathname === '/approvals')!.body).toMatchObject({ decision: 'decline', version: 3 });
  });

  it('disables Accept and Decline when no approval request matches the offer’s version', async () => {
    mockApi({ list_approvals: { ...exampleBody<ApprovalList>('list_approvals'), approvals: [] } });
    openPage('dashboard');
    expect(await screen.findByText(/No approval request for version 3 has reached you yet/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve version 3' })).not.toBeInTheDocument();
  });

  it('counters with one amendment and a reason', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi();
    openPage('dashboard');
    await user.click(await screen.findByRole('button', { name: 'Counter' }));
    const dialog = screen.getByRole('dialog', { name: 'Counter version 3' });
    await user.type(within(dialog).getByLabelText('Pounds we can take'), '150');
    await user.type(within(dialog).getByLabelText('Your reason'), "We need 50 lb of cold space for tomorrow's delivery.");
    await user.click(within(dialog).getByRole('button', { name: 'Send counter' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    const post = calls.find((c) => c.url.pathname === '/lots/lot-market-1013/counters')!;
    // Exactly the contract's example request for submit_counter.
    expect(post.body).toEqual(example('submit_counter').example.request.body);
    expect(await screen.findByText(/Your counter goes in on your organization's next turn/)).toBeInTheDocument();
  });

  it('requires a reason for a counter', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi();
    openPage('dashboard');
    await user.click(await screen.findByRole('button', { name: 'Counter' }));
    const dialog = screen.getByRole('dialog');
    await user.type(within(dialog).getByLabelText('Pounds we can take'), '150');
    const reason = within(dialog).getByLabelText('Your reason');
    reason.removeAttribute('required');
    await user.click(within(dialog).getByRole('button', { name: 'Send counter' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Please give a reason');
    expect(calls.some((c) => c.url.pathname.endsWith('/counters'))).toBe(false);
  });

  it('confirms a pickup by request code and shows the weekly balance', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi();
    openPage('dashboard');
    await user.type(await screen.findByLabelText('Request code'), 'k7p4');
    await user.click(screen.getByRole('button', { name: 'Confirm pickup' }));
    expect(await screen.findByText(/This week: 8 lb of 12 lb fair share received/)).toBeInTheDocument();
    expect(calls.find((c) => c.url.pathname === '/pickup-confirmations')!.body).toEqual({ food_bank_id: 'city', request_code: 'K7P4' });
  });

  it('updates storage, pickup hours, and truck with the contract shape', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi();
    openPage('dashboard');
    await user.click(await screen.findByRole('button', { name: 'Update storage, hours, truck' }));
    const dialog = screen.getByRole('dialog');
    const cold = within(dialog).getByLabelText('Cold free (lb)');
    await user.clear(cold);
    await user.type(cold, '200');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(await screen.findByText(/Saved. Your agent will use these limits from now on/)).toBeInTheDocument();
    const put = calls.find((c) => c.method === 'PUT')!;
    expect(put.url.pathname).toBe('/food-banks/city/status');
    const body = put.body as { storage: { cold_free_lb: number; dry_free_lb: number; window: { start: string } }[]; pickup_windows: unknown[]; truck: unknown };
    expect(body.storage[0]).toMatchObject({ cold_free_lb: 200, dry_free_lb: 200 });
    expect(new Date(body.storage[0].window.start).toISOString()).toBe(new Date('2026-10-13T12:00:00-07:00').toISOString());
    expect(body.pickup_windows).toHaveLength(1);
    expect(body.truck).toMatchObject({ refrigerated: true, capacity_lb: 250 });
  });

  it('records a condition check: approve as use today', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      'POST /lots/lot-market-1013/condition-checks': () => ({
        status: 200,
        body: { mode: 'synthetic', synthetic: true, lot_id: 'lot-market-1013', version: 4, status: 'condition_recorded', committed: false },
      }),
    });
    openPage('dashboard');
    await user.click(await screen.findByRole('button', { name: 'Details, versions, condition' }));
    const check = await screen.findByRole('group', { name: /Condition check: Romaine lettuce/ });
    await user.type(within(check).getByLabelText('What you checked'), 'Cold and crisp on arrival.');
    await user.click(within(check).getByRole('button', { name: 'Save condition check' }));
    expect(await within(check).findByText(/approved as use today/)).toBeInTheDocument();
    const post = calls.find((c) => c.url.pathname.endsWith('/condition-checks'))!;
    expect(post.body).toMatchObject({ organization_id: 'city', version: 3, produce_id: 'romaine', condition_grade: 'use_soon', reason: 'Cold and crisp on arrival.' });
  });

  it('declines a condition check only with a reason', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      'POST /lots/lot-market-1013/condition-checks': () => ({ status: 200, body: { mode: 'synthetic', lot_id: 'lot-market-1013', version: 4, status: 'condition_recorded', committed: false } }),
    });
    openPage('dashboard');
    await user.click(await screen.findByRole('button', { name: 'Details, versions, condition' }));
    const check = await screen.findByRole('group', { name: /Condition check: Romaine lettuce/ });
    await user.click(within(check).getByLabelText('Decline, with a reason'));
    await user.click(within(check).getByRole('button', { name: 'Save condition check' }));
    expect(await within(check).findByRole('alert')).toHaveTextContent('Please give the reason for declining.');
    await user.type(within(check).getByLabelText('Reason for declining'), 'Slimy leaves.');
    await user.click(within(check).getByRole('button', { name: 'Save condition check' }));
    await within(check).findByText(/declined/);
    expect(calls.find((c) => c.url.pathname.endsWith('/condition-checks'))!.body).toMatchObject({ condition_grade: 'not_for_people', reason: 'Slimy leaves.' });
  });

  it('shows a preserved disagreement with each side’s reason', async () => {
    const board = exampleBody<FoodBankDashboard>('get_food_bank_dashboard');
    board.disagreements = [{ lot_id: 'lot-market-1013', reason: '3 rounds without new terms; no automatic commitment' }];
    mockApi({ get_food_bank_dashboard: board });
    openPage('dashboard');
    const section = (await screen.findByRole('heading', { name: 'Disagreements' })).closest('section')!;
    expect(within(section).getByText(/3 rounds without new terms/)).toBeInTheDocument();
    expect(await within(section).findByText(/Farmers market/)).toBeInTheDocument();
    expect(within(section).getByText(/Drop-off to rural and eastside on one route/)).toBeInTheDocument();
    expect(within(section).getByText(/advocate/)).toBeInTheDocument();
    expect(within(section).getByText(/42 households are furthest below fair share/)).toBeInTheDocument();
  });

  it('shows a reason card for every cooler-failure candidate, chosen and rejected', async () => {
    const approvals = exampleBody<ApprovalList>('list_approvals');
    const change = coolerBoard.disruptions[0];
    approvals.approvals.push({
      lot_id: change.lot_id,
      version: change.version,
      terms_hash: change.dashboard.new_version!.terms_hash,
      requested_at: '2026-10-13T15:30:00-07:00',
      expires_at: null,
      why_you: ['proposing_food_bank'],
      summary: 'Romaine moves from City food bank to Eastside food bank.',
      terms: {},
      status: 'awaiting_decision',
      change: 'cooler_failure',
    });
    mockApi({ get_food_bank_dashboard: coolerBoard, list_approvals: approvals });
    openPage('dashboard');
    const section = (await screen.findByRole('heading', { name: 'Disruptions' })).closest('section')!;
    const cards = within(section).getAllByRole('listitem').filter((li) => li.classList.contains('reason-card'));
    expect(cards).toHaveLength(change.dashboard.reason_cards!.length);
    const chosen = cards.find((c) => c.classList.contains('chosen'))!;
    const rejected = cards.find((c) => c.classList.contains('rejected'))!;
    expect(chosen).toHaveTextContent('Eastside food bank');
    expect(chosen).toHaveTextContent('Chosen');
    expect(chosen).toHaveTextContent('15 minutes away');
    expect(rejected).toHaveTextContent('Rural food bank');
    expect(rejected).toHaveTextContent('Not chosen');
    expect(rejected).toHaveTextContent("its pickup hours don't overlap households' pickup time");
    expect(within(section).getByText(/Romaine lettuce: profile says it needs a fridge/)).toBeInTheDocument();
    expect(within(section).getByText(/Apples: profile says it keeps without a fridge/)).toBeInTheDocument();
    expect(within(section).getByText(/Needs fresh approval from:/).parentElement).toHaveTextContent('Eastside food bank');
    expect(within(section).getByRole('button', { name: `Approve version ${change.version}` })).toBeInTheDocument();
    expect(within(section).getByText(/Synthetic scenario data/)).toBeInTheDocument();
  });

  it('hides the disruptions section when the dashboard has none (the skeleton example)', async () => {
    mockApi();
    openPage('dashboard');
    await screen.findByRole('heading', { name: 'City food bank', level: 1 });
    expect(screen.queryByRole('heading', { name: 'Disruptions' })).not.toBeInTheDocument();
  });
});

describe('approvals page', () => {
  it('lists the exact terms and asks for an explicit decision', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi();
    openPage('bank-approvals');
    expect(await screen.findByText(/lot-market-1013, version 3/)).toBeInTheDocument();
    expect(screen.getByText(/Why you: Truck run/)).toBeInTheDocument();
    await user.click(screen.getByText('Exact terms of version 3'));
    expect(screen.getByText('250 lb Apples to Rural food bank')).toBeInTheDocument();
    expect(calls.some((c) => c.method === 'POST')).toBe(false);
  });
});

describe('staff sign-in', () => {
  it('takes the token at runtime, keeps it in this tab, and sends it as a Bearer credential', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi();
    openPage('settings');
    const field = screen.getByLabelText(/Food bank staff token for/);
    expect(field).toHaveAttribute('type', 'password');
    await user.type(field, 'synthetic-city-staff');
    await user.click(within(field.closest('form')!).getByRole('button', { name: 'Save for this tab' }));
    expect(staffToken.get('city')).toBe('synthetic-city-staff');
    expect(field).toHaveValue('');
    expect(window.localStorage.length).toBe(0);
    expect(document.body.textContent).not.toContain('synthetic-city-staff');

    await user.click(within(nav()).getByRole('button', { name: 'Dashboard' }));
    await screen.findByRole('heading', { name: 'City food bank', level: 1 });
    const dashboard = calls.find((c) => c.url.pathname === '/food-banks/city/dashboard')!;
    expect(dashboard.headers.authorization).toBe('Bearer synthetic-city-staff');
  });

  it('explains a 401 without showing the token', async () => {
    staffToken.set('city', 'wrong-token');
    mockApi({ get_food_bank_dashboard: () => ({ status: 401, body: { error: { code: 'unauthorized', message: 'organization staff authentication required' } } }) });
    openPage('dashboard');
    expect(await screen.findByRole('alert')).toHaveTextContent('Staff sign-in needed');
    expect(document.body.textContent).not.toContain('wrong-token');
  });
});

describe('labels', () => {
  it('labels example data as synthetic, from the response’s own mode', async () => {
    mockApi();
    openPage('dashboard');
    await screen.findByRole('heading', { name: 'City food bank', level: 1 });
    expect(screen.getAllByText('Example response from the API skeleton. Every value is synthetic.').length).toBeGreaterThan(0);
  });

  it('labels live data as live', async () => {
    mockApi({ get_food_bank_dashboard: { ...exampleBody<FoodBankDashboard>('get_food_bank_dashboard'), mode: 'live', synthetic: false } });
    openPage('dashboard');
    expect(await screen.findByText('Live API data.')).toBeInTheDocument();
  });
});
