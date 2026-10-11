// The produce split (design section 16, decided by the user October 11, 2026): every pound counts
// once, as collected by households, committed to food banks, or wasted. The numbers are synthetic
// test values in the evaluation runner's shape (harvestnet_core/evaluation.py), not measured results.
import { describe, expect, it } from 'vitest';
import { exampleResults, type MethodResult } from './api';
import { earlierMeasure, produceSplit, wastedLegend } from './split';

const run: MethodResult = {
  method: 'rules_based', status: 'completed', measured: true,
  collected_by_households_lb: 31, committed_to_food_banks_lb: 869, produce_wasted_lb: 0,
  uncollected_by_scenario_households_lb: 869, worst_served_coverage: 0.55, households_reached: 4,
};

describe('produceSplit', () => {
  it('shows collected, committed to food banks, and wasted, in that order, as the API sent them', () => {
    expect(produceSplit(run, 'en')).toEqual([
      { key: 'collected_by_households_lb', label: 'Collected by households', value: 31 },
      { key: 'committed_to_food_banks_lb', label: 'Committed to food banks', value: 869 },
      { key: 'produce_wasted_lb', label: 'Wasted', value: 0 },
    ]);
  });

  it('has Spanish labels', () => {
    expect(produceSplit(run, 'es').map(r => r.label)).toEqual(['Recogido por hogares', 'Comprometido con bancos de alimentos', 'Desperdiciado']);
  });

  it('leaves a missing part missing instead of inventing it', () => {
    const old: MethodResult = { method: 'llm', produce_wasted_lb: 50, worst_served_coverage: 0.6, households_reached: 6 };
    expect(produceSplit(old, 'en').map(r => r.value)).toEqual([null, null, 50]);
  });

  it('keeps the earlier measure visible, labeled as such', () => {
    expect(earlierMeasure(run, 'en')).toEqual({ label: 'Not collected by the scenario households (earlier measure)', value: 869 });
    expect(earlierMeasure(run, 'es')?.label).toBe('No recogido por los hogares del escenario (medida anterior)');
    expect(earlierMeasure({ ...run, uncollected_by_scenario_households_lb: undefined }, 'en')).toBeNull();
  });

  it('the contract example carries the whole split', () => {
    for (const m of exampleResults.methods) expect(produceSplit(m, 'en').every(r => typeof r.value === 'number')).toBe(true);
  });
});

describe('wastedLegend', () => {
  it('says committed produce is not wasted, in English and Spanish', () => {
    expect(wastedLegend.en).toContain('not committed to a food bank that can store it and hand it out before it stops being usable');
    expect(wastedLegend.es).toContain('ni quedaron comprometidas con un banco de alimentos que pueda guardarlas y entregarlas antes de que dejen de servir');
    for (const text of [wastedLegend.en, wastedLegend.es]) expect(text).not.toMatch(/not collected by the end|no recogidas al final/);
  });
});
