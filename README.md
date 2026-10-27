# HarvestNet

**Every food bank and donor gets its own AI agent. They negotiate how surplus produce is shared, so fresh food reaches low-income families instead of the trash, with no central decider.**

Built for the Cisco "When AI Agents Disagree" hackathon track (Level 3). All data in this repository and on the demo site is synthetic.

## The problem

Farms, grocers and farmers markets throw away good produce at closing time while families nearby can't afford it. Food banks could take it, but each one has its own storage, pickup hours and truck, and they compete for the same lots. A central allocator would have to know, and control, every organization's resources. In practice no one hands that control over.

## How HarvestNet works

1. **A household asks** on a phone-friendly web page (English or Spanish, no name, address or income) and picks the food banks it can reach. Its weekly **fair share** comes from a published table by household size, like a SNAP benefit.
2. **A donor reports a surplus lot**, such as apples, romaine and potatoes that must be gone by 3 pm.
3. **Each organization's negotiator bids, counters and explains**, item by item, using only its own facts and calculator results. An advocate pushes produce toward the households furthest below their fair share, but it can't vote. Every change is a new numbered version with a reason.
4. **A staff approver at each organization approves the exact version**, from an email link or the dashboard. Nothing commits automatically. If no version wins every approval, the disagreement is kept and shown, not decided for them.
5. **Households get a pickup email** with their code and a "Can't make it" link that passes the produce to the next family.
6. **When a food bank's cooler fails** (Level 2), its own agent works out which produce must stay cold, finds food banks with cold space through the AGNTCY Directory, writes a reason card for every candidate, and proposes a new version that needs fresh approvals.

The design is in [`docs/MVP_DESIGN.md`](docs/MVP_DESIGN.md), the vocabulary in [`CONTEXT.md`](CONTEXT.md), and the decisions in [`docs/adr/`](docs/adr/).

## Results

The evaluation runs five synthetic scenarios through four methods on the same inputs: first-come-first-served, nearest food bank, rules-based negotiators, and Claude negotiators. It reports produce wasted (each pound counted once: collected, committed to a food bank, or wasted), worst-served fair-share coverage, households reached, and invalid commitments (always zero). The results strip shows whatever the numbers say, including where negotiation does worse, and labels every Claude run as completed, partial or not run.

## Try it

| Screen | Address |
|---|---|
| Household page | https://18-217-110-223.sslip.io/household/ |
| Donor page and food bank dashboards | https://18-217-110-223.sslip.io/donor-dashboard/ |
| Results strip | https://18-217-110-223.sslip.io/results-strip/ |

The demo server is a single small instance and may be offline. The offline recorded replay, [`docs/demo/replay.html`](docs/demo/replay.html), runs from a checkout with no network. Staff screens need an organization's staff token.

## Run it locally

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 18+ and npm. Stop it with `docs/demo/record/start_local_stack.sh down`; the addresses it serves are in [`docs/demo/record/README.md`](docs/demo/record/README.md).

```bash
docs/demo/record/start_local_stack.sh up     # then open http://127.0.0.1:8080/household/
```

Tests for each package:

```bash
cd agents && uv run pytest
```

```bash
cd agents && uv sync && cd .. && PYTHONPATH=agents/src HARVESTNET_PLATFORM_SOURCE=. agents/.venv/bin/python -m unittest discover -s core_tests
```

```bash
uv run --with pytest pytest -q
```

```bash
cd frontend/household && npm ci && npm test
```

## What's where

| Path | What it is |
|---|---|
| `agents/` | Negotiators (rules-based and Claude), produce profiles, fair share, front desk, cooler-failure logic |
| `harvestnet_core/` | Records, calculators, scenario harness, public API, evaluation ([guide](docs/core/README.md)) |
| `harvestnet_platform/` | Organization systems, A2A and Directory transport, approvals, n8n bridge ([guide](docs/platform/)) |
| `frontend/` | Household page, donor page and food bank dashboards, results strip |
| `integrations/` | n8n email workflows and the ElevenLabs voice agent setup |
| `deploy/aws/` | One-command AWS setup, teardown and data reset ([guide](deploy/aws/README.md)) |
| `docs/contracts/` | The agreed API, agent move, calculator and scenario formats |
| `docs/demo/` | Demo script, slides, run sheet, offline replay, recording scripts |

## Built with

Cisco AGNTCY (A2A and the Directory), Claude (negotiators and the voice front desk), n8n Cloud and Amazon SES (approval and pickup emails), ElevenLabs (voice line, being set up), Beeceptor (mock organization systems, with recorded copies as the fallback), AWS.

## Team

[@mubinmodi](https://github.com/mubinmodi), [@calebdbur](https://github.com/calebdbur), [@Haha36](https://github.com/Haha36), [@Gianellerella](https://github.com/Gianellerella).
