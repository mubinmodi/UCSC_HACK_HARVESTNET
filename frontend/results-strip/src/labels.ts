// How each method's card is labeled. Labels only: no number is calculated here.
// The evaluation runner (docs/core/README.md, #24) sends a per-method `status` and `measured`:
// `not_run` (null values), `fallback_only` (no LLM decisions: deterministic fallback outcomes,
// `measured: false`), `partial` (some LLM decisions, some fallbacks) and `completed`.
// A top-level `measured: true` does not make every method measured, so each card checks its own.
import type { MethodResult, Results } from './api';

export type CardStatus = 'not_run' | 'fallback_only' | 'partial' | 'completed' | 'unlabeled' | 'other';

export interface CardLabel {
  status: CardStatus;
  /** The status text the API sent, when it isn't one this page knows. */
  raw?: string;
  /** False when this method's numbers must not be read as a measured result. */
  measured: boolean;
  /** True when the numbers may be shown. Not-run methods show none. */
  showNumbers: boolean;
  reason?: string;
}

const known: CardStatus[] = ['not_run', 'fallback_only', 'partial', 'completed'];

export function cardLabel(results: Results, run: MethodResult | undefined): CardLabel {
  if (!run) return { status: 'not_run', measured: false, showNumbers: false };
  const raw = run.status;
  const status: CardStatus = raw === undefined ? 'unlabeled' : (known as string[]).includes(raw) ? raw as CardStatus : 'other';
  const measured = results.measured === true && results.synthetic !== true && run.measured !== false
    && status !== 'not_run' && status !== 'fallback_only';
  return {
    status,
    raw: status === 'other' ? raw : undefined,
    measured,
    showNumbers: status !== 'not_run',
    reason: run.reason,
  };
}
