// The one place the landing page reads a number: GET /results (docs/contracts/public-api.md).
// Nothing is invented here. If the call fails, or the reply is missing the two figures, the page
// simply leaves the panel out. Like the other apps, it calls `/api` on its own origin (the gateway
// serves the pages and the API together) unless VITE_API_BASE_URL says otherwise.

export interface ResultsGlimpse {
  scenarioId: string;
  runMode: string;
  /** True when the API says the numbers are not measured results, or are synthetic. */
  example: boolean;
  firstComeFirstServed: number;
  rulesBased: number;
}

interface MethodRow { method?: string; status?: string; households_reached?: number | null }
interface ResultsBody {
  scenario_id?: string;
  run_mode?: string;
  measured?: boolean;
  synthetic?: boolean;
  methods?: MethodRow[];
}

const isCount = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

export function glimpseFrom(body: ResultsBody): ResultsGlimpse | null {
  const row = (id: string) => body.methods?.find(m => m.method === id && m.status !== 'not_run');
  const fcfs = row('first_come_first_served')?.households_reached;
  const rules = row('rules_based')?.households_reached;
  if (!isCount(fcfs) || !isCount(rules) || !body.scenario_id) return null;
  return {
    scenarioId: body.scenario_id,
    runMode: body.run_mode ?? 'unknown',
    example: body.measured !== true || body.synthetic === true,
    firstComeFirstServed: fcfs,
    rulesBased: rules,
  };
}

export const DEFAULT_API_BASE_URL = '/api';
export const apiBase = ((import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || DEFAULT_API_BASE_URL).replace(/\/+$/, '');

export async function loadResultsGlimpse(base: string = apiBase, fetcher: typeof fetch = fetch): Promise<ResultsGlimpse | null> {
  if (!base) return null;
  try {
    const response = await fetcher(`${base}/results?scenario_id=normal-afternoon`, { cache: 'no-store' });
    if (!response.ok) return null;
    return glimpseFrom((await response.json()) as ResultsBody);
  } catch {
    return null;
  }
}
