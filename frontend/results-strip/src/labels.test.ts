// Every result shape here mirrors what the evaluation runner sends (harvestnet_core/evaluation.py).
// The numbers are synthetic test values, not measured results.
import { describe, expect, it } from 'vitest';
import { exampleResults, type MethodResult, type Results } from './api';
import { cardLabel } from './labels';

const evaluated = (llm: MethodResult): Results => ({
  scenario_id: 'normal-afternoon',
  run_mode: 'synthetic',
  measured: true,
  methods: [{ method: 'rules_based', status: 'completed', measured: true, produce_wasted_lb: 1, worst_served_coverage: 0.5, households_reached: 2 }, llm],
});

describe('cardLabel', () => {
  it('marks the contract example as not measured', () => {
    for (const run of exampleResults.methods) expect(cardLabel(exampleResults, run)).toMatchObject({ measured: false, showNumbers: true });
  });

  it('shows not_run and a missing method without numbers', () => {
    const run: MethodResult = { method: 'llm', status: 'not_run', reason: 'No authorized capped LLM provider configured', measured: false, produce_wasted_lb: null, worst_served_coverage: null, households_reached: null };
    expect(cardLabel(evaluated(run), run)).toMatchObject({ status: 'not_run', measured: false, showNumbers: false, reason: run.reason });
    expect(cardLabel(evaluated(run), undefined)).toMatchObject({ status: 'not_run', showNumbers: false });
  });

  it('never presents fallback_only as a measured LLM result, even when the response is measured', () => {
    const run: MethodResult = { method: 'llm', status: 'fallback_only', measured: false, reason: 'No LLM decisions occurred in these runs; these are deterministic fallback outcomes', produce_wasted_lb: 3, worst_served_coverage: 0.4, households_reached: 2 };
    expect(cardLabel(evaluated(run), run)).toMatchObject({ status: 'fallback_only', measured: false, showNumbers: true });
    expect(cardLabel(evaluated({ ...run, measured: undefined }), { ...run, measured: undefined }).measured).toBe(false);
  });

  it('labels partial runs and keeps their reason', () => {
    const run: MethodResult = { method: 'llm', status: 'partial', measured: true, reason: '1 rules fallback and 0 template fallback decisions alongside 3 LLM decisions; see each run', produce_wasted_lb: 3, worst_served_coverage: 0.4, households_reached: 2 };
    expect(cardLabel(evaluated(run), run)).toMatchObject({ status: 'partial', measured: true, reason: run.reason });
  });

  it('respects a method-level measured: false and passes unknown statuses through', () => {
    const run: MethodResult = { method: 'llm', status: 'completed', measured: false, produce_wasted_lb: 3, worst_served_coverage: 0.4, households_reached: 2 };
    expect(cardLabel(evaluated(run), run).measured).toBe(false);
    const odd = { ...run, status: 'cancelled', measured: true };
    expect(cardLabel(evaluated(odd), odd)).toMatchObject({ status: 'other', raw: 'cancelled' });
  });

  it('treats completed runs in a measured response as measured', () => {
    const run: MethodResult = { method: 'llm', status: 'completed', measured: true, produce_wasted_lb: 3, worst_served_coverage: 0.4, households_reached: 2 };
    expect(cardLabel(evaluated(run), run)).toMatchObject({ status: 'completed', measured: true });
  });
});
