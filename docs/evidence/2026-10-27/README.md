# HarvestNet evidence bundle — October 27, 2026

Candidate commit: `286c2d9b77208f0d42bba1109d5d44b3b98cc0ef` (`main`, PR #85 merged).

Every scenario and result in this bundle is **synthetic**. The rules and Claude evaluations are measured runs of the real evaluation code against `core_fixtures/*.json`; they are not observed food distribution, field outcomes, or a deployed AWS run. AWS evidence is pending because no `project=harvestnet` resources existed when this bundle was started.

## Reproduce

The deterministic evaluation was run with:

```bash
PYTHONPATH=agents/src HARVESTNET_PLATFORM_SOURCE=. \
agents/.venv/bin/python -m harvestnet_core evaluate \
  --database docs/evidence/2026-10-27/rules.sqlite \
  --output docs/evidence/2026-10-27/rules-replays \
  core_fixtures/*.json
```

The paid evaluation was run once with the repository's existing `$5` per-run and `$50` total caps. No cap was raised:

```bash
PYTHONPATH=agents/src HARVESTNET_PLATFORM_SOURCE=. \
agents/.venv/bin/python -m harvestnet_core evaluate \
  --allow-paid --llm-cap-usd 5 \
  --database docs/evidence/2026-10-27/claude.sqlite \
  --output docs/evidence/2026-10-27/claude-replays \
  core_fixtures/*.json
```

The persistent ledger stopped new reservations before the run could exceed its cap. Actual recorded spend was `$4.9083`.

## Contents

- `rules-evaluation.json`: full deterministic evaluation output.
- `rules-summary.json`: compact metrics for the deterministic evaluation.
- `rules-replays/`: individual FCFS, nearest-food-bank and rules-based replays.
- `claude-evaluation.json`: full paid evaluation output.
- `claude-summary.json`: compact method-level metrics and honest completed/partial labels.
- `claude-run-evidence.json`: per-scenario Claude event counts, safety checks and metrics.
- `claude-replays/`: individual baseline, rules and Claude replays.
- `claude-spend-ledger.json`: sanitized model, timestamp and cost records from this run; it contains no API key.
- `CLAIMS.md`: claim-to-evidence matrix and limitations.
- `SHA256SUMS`: hashes for the principal evidence files.

The SQLite files were transient publication databases and are not evidence; JSON outputs and recorded replays are the portable artifacts.

## Principal findings

- `condition-doubt` is a fully model-driven preserved disagreement: 15 LLM decisions, 21 model calls, zero fallback decisions, zero invalid commitments, and every rule check true.
- `cooler-failure` is partial: 33 LLM decisions and two template fallbacks. It reached five scripted households but wasted 818 synthetic lb, worse than the rules method's 200 synthetic lb.
- `more-households-than-produce` is partial: 34 LLM decisions and six template fallbacks. Its headline metrics equal the rules method.
- `more-produce-than-storage` is partial: 50 LLM decisions, one rules fallback and four template fallbacks. Its headline metrics equal the rules method.
- `normal-afternoon` is partial because the shared cap was nearly exhausted: three LLM decisions and 25 rules fallbacks. Its headline metrics equal the rules method and must not be presented as a Claude result without that qualification.

These results establish that live Claude negotiators execute, use the real calculators, can preserve a disagreement, and stay inside the cap. They do not establish that Claude outperforms the rules or nearest-food-bank methods.
