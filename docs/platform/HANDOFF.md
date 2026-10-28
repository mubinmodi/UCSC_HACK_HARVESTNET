# Platform handoff

The platform (Lane C) is the organization hosts, the organization systems, the approval and email service, the n8n workflows and the AWS deployment. It is merged on `main` and follows the agreed contracts in [`docs/contracts/`](../contracts/README.md).

## What is deployed

The last recorded deploy is in `deploy/aws/outputs.json` on the lead's machine (Git-ignored): instance, host name, git SHA and release. The stack is one EC2 instance in us-east-2, described in [`deploy/aws/README.md`](../../deploy/aws/README.md).

Confirm it is up before relying on it: `curl https://<host>/api/health` and `https://<host>/platform/health`, then `deploy/aws/logs.sh` and `deploy/aws/check_directory.sh`. If it was torn down, `deploy/aws/setup.sh` recreates it.

| Piece | Where it lives |
|---|---|
| Core API and frontends | `https://<host>/api/`, `/household/`, `/donor-dashboard/`, `/results-strip/` |
| Organization hosts, Directory, cooler watchers | Containers on the instance ([`TRANSPORT.md`](TRANSPORT.md)) |
| Review links and email preparation | `approvals` container ([`APPROVALS.md`](APPROVALS.md)) |
| Organization systems and the cooler switch | `systems` container ([`CONTRACTS.md`](CONTRACTS.md)) |
| Emails | n8n Cloud and Amazon SES (team account) |
| Organization data | Beeceptor, from `BEECEPTOR_BASE_URL`; recorded copies when unset or mismatched |

## n8n Cloud

Three workflows are active and carry all live email: review requests (`x3dsVytciPRThmlX`), committed pickup emails (`9qaAaWdqvIEzn4T4`) and the release thank-you (`g0qO8uMLOBIwpYi4`). Keep any other HarvestNet workflow in that project inactive. The older drafts include an SMS reply workflow, a human-decision relay and a manual Beeceptor check; the SMS path is retired. These are workflow IDs, not credentials. The workflow definitions in `integrations/n8n/` are generated references, not the live copies. Setup: [`APPROVALS.md`](APPROVALS.md).

## How to operate it

- **Redeploy, logs, reset, teardown, keys:** `deploy/aws/README.md`. Team commands and the rehearsal flow: `docs/demo/REHEARSAL.md`, `docs/demo/run-sheet.html`, `docs/demo/team-checklist.html`.
- **Run the cooler failure live:** flip the switch with the `DEMO_SWITCH_TOKEN` bearer (`docs/demo/REHEARSAL.md`). The food bank's own watcher does the rest and asks the Staff approvers to approve on their review links.
- **Spending:** every paid Claude call needs a cap above zero ([`DEPLOYMENT.md`](DEPLOYMENT.md)). Keep every shown number labeled synthetic.
- **Local checks:** `uv run --with pytest pytest -q` at the root; `python -m harvestnet_platform.demo` for the account-free rehearsal.

## What is open

Tickets and their checklists are the live list: GitHub issues on `mubinmodi/UCSC_HACK_HARVESTNET`. The platform's open items:

- **Email end to end.** Send a real pickup email, review email and release thank-you through SES to verified recipients and confirm delivery. SES is sandboxed, so only verified addresses receive mail.
- **Beeceptor mock on the current fixture.** Re-import it from `python -m harvestnet_platform.systems --export-openapi` if the fixture version changed; until then reads fall back to recorded copies ([`CONTRACTS.md`](CONTRACTS.md)).
- **Directory on the instance.** Run `deploy/aws/check_directory.sh` after each deploy. Whether all five hosts republish after a cooler change, and the memory use, are checked there, not assumed.
- **A live lot over A2A on the instance.** The core now requests every live move from the organization's own host over signed A2A (`HARVESTNET_MOVE_TRANSPORT=a2a` in `deploy/aws/compose.aws.yaml`; [`TRANSPORT.md`](TRANSPORT.md), "Move requests"). It is tested end to end on localhost (`core_tests/test_a2a_moves.py`), not yet on a deployed stack: after the next deploy, create an offer and check that `GET /api/lots/<lot_id>/versions` lists every move as `a2a`, and read the core log for `IN-PROCESS FALLBACK` lines.
- **Voice line.** The ElevenLabs agent and a live call (issues #4 and #22). Voice intake answers 503 until `ANTHROPIC_API_KEY` and a run cap are set.
- **Paid evaluation runs.** More repeats within the agreed budget (issue #24); see `docs/core/README.md`, Evaluation.
- **Seed the Claude spend ledger after a fresh `setup.sh`.** The total cap is enforced against the ledger, which `teardown.sh` deletes ([`DEPLOYMENT.md`](DEPLOYMENT.md)).
