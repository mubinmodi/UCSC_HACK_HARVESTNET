import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { apiBase, glimpseFrom, loadResultsGlimpse } from '../results';

// The page asks the results API on mount; with no network in tests, that call fails and the panel is left out.
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
});

describe('landing page', () => {
  it('explains the project and has the sections the lead asked for', () => {
    render(<App />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Fresh food for families, not the trash.');
    expect(screen.getByText(/no central decider/)).toBeInTheDocument();
    for (const name of [/Good produce is wasted/, 'How it works', 'What it does', 'Who it is for', 'Honest results']) {
      expect(screen.getByRole('heading', { level: 2, name })).toBeInTheDocument();
    }
    expect(screen.getByText('Cisco AGNTCY')).toBeInTheDocument();
    expect(screen.getByText('n8n')).toBeInTheDocument();
  });

  it('links the wordmark to the site root and the calls to action to the apps', () => {
    render(<App />);
    expect(screen.getAllByRole('link', { name: 'HarvestNet' })[0]).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: /Ask for produce/ })).toHaveAttribute('href', '/household/');
    expect(screen.getByRole('link', { name: 'Donors and food banks' })).toHaveAttribute('href', '/donor-dashboard/');
    expect(screen.getByRole('link', { name: 'See results' })).toHaveAttribute('href', '/results-strip/');
    expect(screen.getByText('Households need no account, name or address.')).toBeInTheDocument();
  });

  it('opens a login chooser that says households need no account', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole('button', { name: 'Log in' }));
    const dialog = screen.getByRole('dialog', { name: 'Log in' });
    expect(within(dialog).getByText(/no user accounts/)).toBeInTheDocument();
    expect(within(dialog).getByRole('link', { name: /I’m a household/ })).toHaveAttribute('href', '/household/');
    expect(within(dialog).getByRole('link', { name: /Donor or food bank staff/ })).toHaveAttribute('href', '/donor-dashboard/');
    expect(within(dialog).getByRole('link', { name: /See results/ })).toHaveAttribute('href', '/results-strip/');
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Log in' })).toHaveFocus();
  });

  it('keeps keyboard focus inside the login chooser', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole('button', { name: 'Log in' }));
    const dialog = screen.getByRole('dialog', { name: 'Log in' });
    const stops = [...dialog.querySelectorAll<HTMLElement>('a[href], button')];
    expect(stops[0]).toHaveFocus();
    await user.tab({ shift: true });
    expect(stops[stops.length - 1]).toHaveFocus();
    await user.tab();
    expect(stops[0]).toHaveFocus();
  });

  it('switches to Spanish', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole('button', { name: 'Cambiar a español' }));
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Comida fresca para las familias');
    expect(document.documentElement.lang).toBe('es');
    expect(screen.getByRole('button', { name: 'Iniciar sesión' })).toBeInTheDocument();
  });

  it('credits the photographer and the license in the footer', () => {
    render(<App />);
    const footer = screen.getByRole('contentinfo');
    expect(within(footer).getByRole('link', { name: 'Ashley Winkler' })).toHaveAttribute('href', 'https://unsplash.com/@firlefanzski');
    expect(within(footer).getByText(/Unsplash License/)).toBeInTheDocument();
    expect(within(footer).getByRole('link', { name: /Source code on GitHub/ })).toHaveAttribute('href', 'https://github.com/mubinmodi/UCSC_HACK_HARVESTNET');
  });

  it('shows no figures when the results API does not answer', () => {
    render(<App />);
    expect(screen.queryByText(/households reached/)).not.toBeInTheDocument();
  });

  it('shows the two counts, labeled synthetic, when the results API answers', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({
      scenario_id: 'normal-afternoon', run_mode: 'synthetic', measured: false, synthetic: true,
      methods: [{ method: 'first_come_first_served', households_reached: 3 }, { method: 'rules_based', households_reached: 4 }],
    }) }));
    render(<App />);
    const panel = await screen.findByRole('group', { name: /From the results API/ });
    expect(within(panel).getByText('Synthetic')).toBeInTheDocument();
    expect(within(panel).getByText(/Example data, not a measured result/)).toBeInTheDocument();
  });

  it('has no personal email address anywhere on the page', () => {
    const { container } = render(<App />);
    expect(container.textContent).not.toMatch(/[\w.+-]+@[\w-]+\.[\w.]+/);
  });
});

describe('results glimpse', () => {
  const body = {
    scenario_id: 'normal-afternoon', run_mode: 'synthetic', measured: false, synthetic: true,
    methods: [
      { method: 'first_come_first_served', households_reached: 3 },
      { method: 'rules_based', households_reached: 4 },
    ],
  };

  it('reads the two household counts from the API and labels example data', () => {
    expect(glimpseFrom(body)).toEqual({
      scenarioId: 'normal-afternoon', runMode: 'synthetic', example: true, firstComeFirstServed: 3, rulesBased: 4,
    });
  });

  it('leaves the panel out when a figure is missing or a method was not run', () => {
    expect(glimpseFrom({ ...body, methods: [{ method: 'first_come_first_served', households_reached: 3 }] })).toBeNull();
    expect(glimpseFrom({ ...body, methods: [{ method: 'first_come_first_served', households_reached: 3 }, { method: 'rules_based', status: 'not_run', households_reached: 4 }] })).toBeNull();
  });

  it('calls /api on its own origin by default', () => {
    expect(apiBase).toBe('/api');
  });

  it('fetches only when an address is given, and swallows failures', async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => body });
    expect(await loadResultsGlimpse('', fetcher)).toBeNull();
    expect(fetcher).not.toHaveBeenCalled();
    expect((await loadResultsGlimpse('https://x.test/api', fetcher))?.rulesBased).toBe(4);
    expect(fetcher).toHaveBeenCalledWith('https://x.test/api/results?scenario_id=normal-afternoon', { cache: 'no-store' });
    expect(await loadResultsGlimpse('https://x.test/api', vi.fn().mockRejectedValue(new Error('down')))).toBeNull();
  });
});
