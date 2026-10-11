// Results adapter for GET /results (docs/contracts/public-api.md, "Results").
// Set VITE_API_BASE_URL to read the real API. Without it, the page uses the contract's
// example response (docs/contracts/examples/public-api/get_results.json). Every example value is synthetic.

export type MethodId = 'first_come_first_served' | 'nearest_food_bank' | 'rules_based' | 'llm';
export type RunMode = 'live' | 'replay' | 'synthetic';

export interface MethodResult {
  method: MethodId | string;
  status?: string; // the evaluation runner sends "not_run" for a method it didn't run
  reason?: string;
  measured?: boolean;
  // Each offered pound counts once in these three (design section 16, October 11, 2026).
  collected_by_households_lb?: number | null;
  committed_to_food_banks_lb?: number | null; // beyond the households' pickups, with storage and pickup hours in time
  produce_wasted_lb: number | null; // no pathway at the scenario end
  uncollected_by_scenario_households_lb?: number | null; // the earlier "produce wasted"
  worst_served_coverage: number | null; // a share from 0 to 1, as the API sends it
  households_reached: number | null;
  invalid_commitments?: number | null;
}

export interface Results {
  mode?: string;
  synthetic?: boolean;
  scenario_id: string;
  run_mode: RunMode | string;
  measured: boolean;
  note?: string;
  methods: MethodResult[];
  headline?: string[];
}

export const exampleResults: Results = {
  mode: 'example',
  synthetic: true,
  scenario_id: 'normal-afternoon',
  run_mode: 'synthetic',
  measured: false,
  note: 'Example values for building the results strip. Not a measured result.',
  methods: [
    { method: 'first_come_first_served', collected_by_households_lb: 40, committed_to_food_banks_lb: 650, produce_wasted_lb: 210, uncollected_by_scenario_households_lb: 860, worst_served_coverage: 0.25, households_reached: 5, invalid_commitments: 0 },
    { method: 'nearest_food_bank', collected_by_households_lb: 45, committed_to_food_banks_lb: 675, produce_wasted_lb: 180, uncollected_by_scenario_households_lb: 855, worst_served_coverage: 0.31, households_reached: 5, invalid_commitments: 0 },
    { method: 'rules_based', collected_by_households_lb: 60, committed_to_food_banks_lb: 780, produce_wasted_lb: 60, uncollected_by_scenario_households_lb: 840, worst_served_coverage: 0.58, households_reached: 6, invalid_commitments: 0 },
    { method: 'llm', collected_by_households_lb: 62, committed_to_food_banks_lb: 788, produce_wasted_lb: 50, uncollected_by_scenario_households_lb: 838, worst_served_coverage: 0.62, households_reached: 6, invalid_commitments: 0 },
  ],
  headline: ['produce_wasted_lb', 'worst_served_coverage'],
};

const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '');

export const resultsApi = {
  source: baseUrl ? `${baseUrl}/results` : 'example response (no API address set)',
  async load(scenarioId = 'normal-afternoon'): Promise<Results> {
    if (!baseUrl) return structuredClone(exampleResults);
    const response = await fetch(`${baseUrl}/results?scenario_id=${encodeURIComponent(scenarioId)}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  },
};
