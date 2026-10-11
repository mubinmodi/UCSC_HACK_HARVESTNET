# HarvestNet contracts (ticket #1)

**Status: Agreed (team, October 11, 2026; recorded by Claude at the leader's direction).** The public API is now `contract-v0.2` (decision 14); the other three contracts are still `contract-v0.1`. Drafted by Claude from the design (`docs/MVP_DESIGN.md`), the ADRs, and the code already written in Lanes B and C. To change a contract now, raise it on ticket #1 or in a PR, and update the examples and tests with it.

These are the four shared interfaces. Every lane builds and tests against them and nobody waits on anybody (`.scratch/harvestnet-mvp/lanes.md`).

| Contract | What it fixes | Owner | Examples |
|---|---|---|---|
| [Scenario fixtures](scenario-fixtures.md) | The format of a scripted day the harness runs | Lane A | [`examples/scenario-normal-afternoon.json`](examples/scenario-normal-afternoon.json) |
| [Agent moves](agent-moves.md) | What a negotiator gets and what it may return | Lanes A and B | [`examples/agent-moves.json`](examples/agent-moves.json) |
| [Calculators](calculators.md) | The named calculators, with inputs and outputs | Lane A | [`examples/calculators.json`](examples/calculators.json) |
| [Public API](public-api.md) | Every web, voice, approval, and results operation | Lane C and the frontend | [`examples/public-api/`](examples/public-api/) |

The **API skeleton** in `api_skeleton/` serves the public API examples at their documented routes, so the frontend can build screens now. Lane A later swaps in real logic behind the same routes and shapes.

## Rules that apply to all four

- **Words.** Use `CONTEXT.md` terms: organization, specialist, negotiator, donor, food bank, advocate, request, surplus lot, draft agreement, hold, commitment, preserved disagreement, fair share, coverage, pathway. JSON keys are `snake_case` versions of them.
- **Numbers are synthetic.** Every example number is made up for testing (ADR 0002). Every example file says `"synthetic": true`. No example is a measured result.
- **Numbers come from calculators.** No agent and no API response invents a quantity, capacity, or time (ADR 0002).
- **Nothing commits by itself.** A commitment needs every named organization's human to approve the same version (ADR 0001). No move, API call, or deadline commits anything on its own.
- **Times** are ISO 8601 with a UTC offset, for example `2026-10-13T15:00:00-07:00`. A household's pickup windows are the one exception: they repeat weekly, so they use days plus local clock times (`"18:00"`).
- **Pounds** are plain numbers in fields named `pounds` or ending in `_lb`. Other units are converted by the unit calculator.
- **IDs.** Organizations use short lowercase IDs (`market`, `city`, `rural`, `eastside`, `advocate`). A role (`donor`, `food_bank`, `advocate`) is a separate field, never the ID. Produce uses its profile ID (`apples`, `romaine`). A request uses a short code (`K7P4`).
- **Privacy.** No names, addresses, or income. An email address is optional, write-only, used only for pickup emails, never returned or logged, and deleted with the request after 7 days. Agents and food banks see households only as counts (`docs/MVP_DESIGN.md` §12).
- **Labels.** Every API response carries `mode`: `example` (the skeleton), `live`, `replay`, or `synthetic`, so nobody mistakes example data for a real run.

## Decisions made

The existing code disagreed in a few places. The team agreed these choices with the contracts.

1. **Organization IDs are names, not roles.** Lane B uses `market` for the donor; Lane C's systems fixture uses `donor`. Chosen: `market`, with `role: "donor"` alongside. Lane C's join already has a `LANE_B_ORGANIZATION_IDS` alias, which can then be dropped.
2. **Times carry an offset.** Lane B's fixtures use local times with no offset (`2026-10-13T15:00`); Lane C uses UTC with `Z`. Chosen: ISO 8601 with an offset everywhere. Lane B's code already reads offset times and gives the same moves (checked by running the #11 negotiators on offset copies of their fixtures).
3. **One scenario date.** Lane B uses October 13, 2026; Lane C's systems fixture uses October 11. Chosen: October 13, 2026, in Pacific time (`-07:00`). Lane C's systems fixture would be re-dated.
4. **Field names follow Lane B.** `produce_id` (not `profile_id`), `condition_grade` (not `condition`), `cold_free_lb` and `dry_free_lb` (not `cold_available_lb`), `cant_eat` (not `cannot_eat`). Lane C's Beeceptor mocks describe each organization's own systems, so they may keep their own field names; specialists translate them into these facts.
5. **Agent input is Lane B's shape.** A negotiator receives `{role, draft, facts, turn}` with a full typed draft and a `turn` object. Lane C's transport envelope (`event_id`, `sequence`) wraps this input and doesn't replace it. The move output is Lane B's `Move.to_dict()`, which already matches Lane C's wire shape.
6. **`pass` is a sixth move.** Ticket #1 lists five moves. Lane B added `pass` so the advocate can take its turn without voting; Lane C accepts it. Chosen: keep it. The advocate may only `counter` or `pass`.
7. **One event per surplus lot.** Lane C says `event_id`; Lane B says `lot_id`. They name the same thing (`CONTEXT.md`: an event is one surplus lot's journey). Chosen: the API uses `lot_id`, and Lane C's `event_id` carries the lot ID.
8. **Approvals use Lane C's receipt.** `POST /approvals` takes `lot_id`, `version`, `organization_id`, `terms_hash`, `decision`, and an optional `receipt_id`, matching what Lane C's approval bridge already sends to the core, except that its `event_id` field is named `lot_id`.
9. **"Can't make it" uses Lane C's route.** `POST /pickups/{pickup_id}/release` with the request code in the body.
10. **Household portion is a new calculator.** Lane B's stand-ins have no portion calculator. Rule: fill the households furthest below fair share first, evening out the pounds still owed, and never go above fair share. Lane A owns it in #8.
11. **The household shows its request code at pickup.** There's no separate pickup code. Staff enter the request code, and the API finds that household's open pickup at their food bank.
12. **Auth is deferred.** The skeleton has no login. The real API needs staff sign-in for dashboards and approvals, and a pickup-bound token for releases (Lane C's design). That's for #9 and #19.
13. **No expected winner in fixtures.** A scenario lists the rule checks to run but no expected split (ADR 0005). The split follows the run.
14. **Pickup messages go by email, not SMS (`contract-v0.2`).** **Decided (user, October 11, 2026).** SMS needed Twilio and US carrier (A2P 10DLC) registration. Email goes out through n8n's Send Email (SMTP) node with Amazon SES in the team's AWS account. `create_request` takes an optional `email` instead of `phone` (`phone` is refused with 400) and returns `emails` instead of `texts`. Pickup emails carry a *Can't make it* link to the household page, which calls `release_pickup` unchanged; the SMS reply path is gone. The voice line still collects no contact. `get_health` reports `contract-v0.2`.

## What's left for ticket #1

- Deploy the API skeleton on AWS Lambda with an HTTPS Function URL ([`api_skeleton/DEPLOY.md`](../../api_skeleton/DEPLOY.md)). Not done here; the team leader deploys.
- The frontend person calls the deployed skeleton from a browser and sees example data.
