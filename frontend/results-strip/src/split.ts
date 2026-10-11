// Where each offered pound ended up (docs/MVP_DESIGN.md section 16, decided by the user
// October 11, 2026). Labels only: every number is the API's, as sent. Each pound counts once:
// collected by households, else committed to a food bank that can store it and hand it out
// before it stops being usable, else wasted.
import type { MethodResult } from './api';

export type Language = 'en' | 'es';

export type SplitKey = 'collected_by_households_lb' | 'committed_to_food_banks_lb' | 'produce_wasted_lb';

const parts: [SplitKey, string, string][] = [
  ['collected_by_households_lb', 'Collected by households', 'Recogido por hogares'],
  ['committed_to_food_banks_lb', 'Committed to food banks', 'Comprometido con bancos de alimentos'],
  ['produce_wasted_lb', 'Wasted', 'Desperdiciado'],
];

export interface SplitRow {
  key: SplitKey;
  label: string;
  value: number | null;
}

// An older API response uses produce_wasted_lb for pounds not collected by the scenario's
// households. Require the new split before displaying that field with its new meaning.
export function hasProduceSplit(run: MethodResult): boolean {
  return parts.every(([key]) => typeof run[key] === 'number');
}

export function produceSplit(run: MethodResult, language: Language): SplitRow[] {
  const complete = hasProduceSplit(run);
  return parts.map(([key, en, es]) => ({ key, label: language === 'es' ? es : en, value: complete ? run[key] ?? null : null }));
}

/** The earlier "produce wasted" (everything the scenario's households didn't collect), kept so the change is visible. */
export function earlierMeasure(run: MethodResult, language: Language): { label: string; value: number } | null {
  // Before the split was added, produce_wasted_lb carried exactly this earlier measure.
  const value = run.uncollected_by_scenario_households_lb ?? (!hasProduceSplit(run) ? run.produce_wasted_lb : null);
  if (value === null || value === undefined) return null;
  return {
    label: language === 'es' ? 'No recogido por los hogares del escenario (medida anterior)' : 'Not collected by the scenario households (earlier measure)',
    value,
  };
}

export const wastedLegend: Record<Language, string> = {
  en: 'pounds with no pathway at the end of the scenario: not collected by a household, and not committed to a food bank that can store it and hand it out before it stops being usable. Lower is better. Each pound counts once: collected by households, committed to food banks, or wasted.',
  es: 'libras sin destino al final del escenario: no las recogió un hogar ni quedaron comprometidas con un banco de alimentos que pueda guardarlas y entregarlas antes de que dejen de servir. Menos es mejor. Cada libra cuenta una sola vez: recogida por hogares, comprometida con bancos de alimentos o desperdiciada.',
};
