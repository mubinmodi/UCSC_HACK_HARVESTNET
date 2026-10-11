import { render, screen, within } from '@testing-library/react';
import userEvent, { type UserEvent } from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import App from '../App';
import { API_BASE_URL } from '../api';
import { examples, HOUSEHOLD_OPERATIONS, mockApi, operationFor, type Override, type RecordedCall } from './contract';

const body = (op: string) => JSON.parse(JSON.stringify(examples[op].example.response.body));

/** Fill screen 1 with the same answers as the contract examples (preview_request.json). */
async function fillHousehold(user: UserEvent, opts: { phone?: string } = {}) {
  const more = screen.getByRole('button', { name: 'One more person' });
  for (let i = 0; i < 4; i++) await user.click(more);
  await user.click(within(screen.getByRole('group', { name: /Which days/ })).getByRole('radio', { name: 'Weekdays' }));
  await user.click(within(screen.getByRole('group', { name: /What time/ })).getByRole('radio', { name: /Evening/ }));
  await user.click(within(screen.getByRole('group', { name: /fridge/ })).getByRole('radio', { name: 'Yes' }));
  await user.type(screen.getByLabelText(/neighborhood/i), 'Watsonville');
  await user.type(screen.getByLabelText(/can't eat/i), 'eggplant');
  await user.click(within(screen.getByRole('group', { name: /SNAP/ })).getByRole('radio', { name: 'Yes' }));
  if (opts.phone) await user.type(screen.getByLabelText(/Phone number/), opts.phone);
}

async function toFoodBanks(user: UserEvent) {
  await fillHousehold(user, { phone: '(555) 555-0142' });
  await user.click(screen.getByRole('button', { name: 'Review my answers' }));
  await user.click(await screen.findByRole('button', { name: 'Yes, save my answers' }));
  await screen.findByRole('heading', { level: 1, name: 'Choose your food banks' });
}

async function toPickup(user: UserEvent) {
  await toFoodBanks(user);
  await user.click(await screen.findByRole('checkbox', { name: 'Rural food bank' }));
  await user.click(screen.getByRole('checkbox', { name: 'City food bank' }));
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  await screen.findByRole('heading', { level: 1, name: 'Your pickup' });
}

function opsCalled(calls: RecordedCall[]) {
  return calls.map(c => operationFor(c.method, c.url.pathname)?.operation);
}

describe('household page against the contract examples', () => {
  it('runs the whole flow, and every call matches a contract example exactly', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi();
    render(<App />);

    await toPickup(user);
    await user.click(await screen.findByRole('button', { name: "Can't make it" }));
    await user.click(screen.getByRole('button', { name: "Yes, I can't make it" }));
    expect(await screen.findByText(body('release_pickup').message)).toBeInTheDocument();

    expect(new Set(opsCalled(calls))).toEqual(new Set(HOUSEHOLD_OPERATIONS));
    for (const call of calls) {
      const op = operationFor(call.method, call.url.pathname);
      expect(op, `${call.method} ${call.url.pathname} is not a contract route`).toBeDefined();
      const req = op!.example.request;
      expect(call.url.origin + call.url.pathname).toBe(API_BASE_URL + req.path);
      expect(Object.fromEntries(call.url.searchParams)).toEqual(req.query ?? {});
      expect(call.body).toEqual(req.body);
    }
  });

  it('shows the read-back and consent question from the API, and saves nothing without a yes', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi();
    render(<App />);
    await fillHousehold(user, { phone: '5555550142' });
    await user.click(screen.getByRole('button', { name: 'Review my answers' }));

    expect(await screen.findByText(body('preview_request').read_back)).toBeInTheDocument();
    expect(screen.getByText(body('preview_request').consent_question)).toBeInTheDocument();
    // The skeleton's example reply is labelled as such.
    expect(screen.getByText(/Example reply: it may not match your answers/)).toBeInTheDocument();
    // The phone number is only sent with consent, never in the preview.
    const preview = calls.find(c => c.url.pathname === '/requests/preview')!;
    expect(preview.body).not.toHaveProperty('phone');

    await user.click(screen.getByRole('button', { name: "No, don't save" }));
    expect(screen.getByRole('heading', { level: 1, name: 'Nothing was saved' })).toBeInTheDocument();
    expect(calls.some(c => c.method === 'POST' && c.url.pathname === '/requests')).toBe(false);
  });

  it('asks again instead of guessing when required answers are missing', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi();
    render(<App />);
    await user.click(screen.getByRole('button', { name: 'Review my answers' }));
    expect(screen.getByText('Please answer the questions marked below.')).toBeInTheDocument();
    expect(screen.getAllByText('Please answer this question.')).toHaveLength(5);
    expect(calls).toHaveLength(0);
  });

  it('shows the fair share sentence exactly as the API sends it (never calculates it)', async () => {
    const user = userEvent.setup();
    const override: Override = op =>
      op === 'get_fair_share' ? { status: 200, body: { ...body('get_fair_share'), fair_share_lb: 99, wording: 'Synthetic share: 99 lb a week.' } } : undefined;
    const { calls } = mockApi(override);
    render(<App />);
    await user.click(screen.getByRole('button', { name: 'One more person' }));
    expect(await screen.findByText('Synthetic share: 99 lb a week.')).toBeInTheDocument();
    expect(calls[0].url.searchParams.get('household_size')).toBe('1');
    expect(screen.getByText('This amount is an example for now.')).toBeInTheDocument();
  });

  it('labels example data from the skeleton', async () => {
    const user = userEvent.setup();
    mockApi();
    render(<App />);
    await user.click(screen.getByRole('button', { name: 'One more person' }));
    expect(await screen.findByText(/test server sent made-up example answers/)).toBeInTheDocument();
  });

  it('never asks for a name, address, income, or immigration status', () => {
    mockApi();
    const { container } = render(<App />);
    const forbidden = /\b(name|address|street|income|salary|wage|immigra|citizen|ssn|social security|birth)/i;
    const asked = [
      ...Array.from(container.querySelectorAll('label, legend')).map(el => el.textContent ?? ''),
      ...Array.from(container.querySelectorAll('input, textarea')).map(el => `${el.getAttribute('name') ?? ''} ${el.id}`),
    ];
    for (const text of asked) {
      // The neighborhood hint says "Not your street address": that's a hint, not a question.
      expect(text).not.toMatch(forbidden);
    }
    expect(container.querySelectorAll('input[autocomplete="name"], input[autocomplete*="address"]')).toHaveLength(0);
  });

  it('lists only committed produce on the pickup screen', async () => {
    const user = userEvent.setup();
    const status = body('get_request');
    const committed = status.pickups[0];
    status.pickups = [
      committed,
      { ...committed, pickup_id: 'pk-negotiating', food_bank_name: 'Still negotiating bank', status: 'negotiating', wording: 'NOT COMMITTED' },
      { ...committed, pickup_id: 'pk-held', food_bank_name: 'Held bank', status: 'held', wording: 'ONLY HELD' },
    ];
    mockApi(op => (op === 'get_request' ? { status: 200, body: status } : undefined));
    render(<App />);
    await toPickup(user);
    expect(await screen.findByText(committed.wording)).toBeInTheDocument();
    expect(screen.queryByText('NOT COMMITTED')).not.toBeInTheDocument();
    expect(screen.queryByText('ONLY HELD')).not.toBeInTheDocument();
    // The request code is the pickup code (contract decision 11), and the balance comes from the API.
    expect(screen.getAllByText('K7P4').length).toBeGreaterThan(0);
    expect(screen.getByText('This week: 0 of 12 lb received')).toBeInTheDocument();
  });

  it('shows committed produce and badges on the food bank screen', async () => {
    const user = userEvent.setup();
    mockApi();
    render(<App />);
    await toFoodBanks(user);
    const city = (await screen.findByRole('checkbox', { name: 'City food bank' })).closest('.bank-card') as HTMLElement;
    expect(within(city).getByText('Romaine lettuce · 200 lb')).toBeInTheDocument();
    expect(within(city).getByText('Keep cold')).toBeInTheDocument();
    expect(within(city).getByText('Use within 2 days')).toBeInTheDocument();
    const eastside = screen.getByRole('checkbox', { name: 'Eastside food bank' }).closest('.bank-card') as HTMLElement;
    expect(within(eastside).getByText('Nothing confirmed here yet.')).toBeInTheDocument();
  });

  it('shows a plain error with "Try again" when the API is busy, and recovers', async () => {
    const user = userEvent.setup();
    let fail = true;
    mockApi(op => (op === 'preview_request' && fail ? { status: 503, body: { error: { code: 'unavailable', message: 'busy' } } } : undefined));
    render(<App />);
    await fillHousehold(user);
    await user.click(screen.getByRole('button', { name: 'Review my answers' }));
    expect(await screen.findByText('HarvestNet is busy right now. Please try again in a moment.')).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('button', { name: 'Yes, save my answers' })).toBeInTheDocument();
  });

  it('works in Spanish and asks the API in Spanish', async () => {
    const user = userEvent.setup();
    const { calls } = mockApi();
    render(<App />);
    await user.click(screen.getByRole('button', { name: 'Cambiar a español' }));
    expect(screen.getByRole('heading', { level: 1, name: 'Sobre su hogar' })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe('es');
    await user.click(screen.getByRole('button', { name: 'Una persona más' }));
    await screen.findByText(body('get_fair_share').wording);
    expect(calls.at(-1)!.url.searchParams.get('language')).toBe('es');
    expect(screen.getByRole('group', { name: /SNAP/ })).toHaveTextContent('Prefiero no decirlo');
  });
});
