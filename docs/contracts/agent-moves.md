# Agent move interface

**Status: Agreed (team, October 11, 2026; recorded by Claude at the leader's direction).** Owners: Lanes A and B. Synced with Lane B's rules-based negotiators (#11, PR #34, commit `f06b148`): this contract describes `agents/src/harvestnet_agents/negotiation.py` on that branch, and Lane C's transport (PR #27) already carries the same move shape. Shared rules are in the [README](README.md).

On its turn, a **negotiator** gets three things: the current **draft version**, its own **specialists' facts**, and the **turn**. It returns exactly one **move**. Rules-based (#11) and LLM (#13) negotiators use this same interface, so the harness can swap them.

Examples: [`examples/agent-moves.json`](examples/agent-moves.json), four input/output pairs. Each output was produced by actually running the #11 negotiators on the input shown.

| Example | Who | Move |
|---|---|---|
| `food_bank_counters_on_cold_storage` | City food bank | `counter`: 50 lb less romaine, because its cold space is short |
| `advocate_shifts_toward_largest_gap` | Advocate | `counter`: shift 160 lb of potatoes to the food bank furthest below fair share |
| `donor_asks_human_on_condition_doubt` | Farmers market | `ask_human`: the romaine's cold chain is unknown |
| `donor_requests_holds` | Farmers market | `request_hold`: its own lot and drop-off slot, after everyone accepted |

All numbers in them are synthetic. More recorded pairs (26 in all, one per rule) are in #11's `agents/tests/fixtures/negotiators/`.

Food banks may now bid beyond fair share once their households' gap is met (user direction, October 11, 2026). That changes which moves a food bank makes, not this interface: an extra bid is an ordinary `counter` with `set_pounds`, and its `reason` says "beyond fair share". Re-running the four examples above after that change gives the same outputs, so they are unchanged (an `agents` test checks this).

## Input

```json
{"role": "food_bank", "draft": {...}, "facts": {...}, "turn": {...}}
```

### `draft`: one version of the draft agreement

| Field | Meaning |
|---|---|
| `lot_id`, `version` | Which surplus lot, and which numbered version. |
| `based_on_version`, `proposer_id`, `reason` | Where this version came from and why. |
| `donor_id`, `deadline` | The donor, and when the produce must leave it. |
| `items` | The lot, item by item: `produce_id`, `pounds`, `condition_grade`, `usable_until`, and optional `condition_doubt`. |
| `allocations` | How many pounds of which item go to which food bank: `produce_id`, `food_bank_id`, `pounds`. Unallocated pounds are the lot's unclaimed pounds. |
| `transports` | Who moves each food bank's share: `food_bank_id`, `mover` (`donor` drops off or `food_bank` collects), `departs_at`, `arrives_at`. |
| `drop_off_to`, `drop_off_refrigerated` | Where the donor offered to drop off, and whether that run keeps a cold chain. |
| `names` | Display names by organization ID. |

A draft can't allocate more of an item than the lot holds, and each food bank has at most one transport line.

### `facts`: this organization's own specialists' facts, and nobody else's

- **Donor:** `donor_id`, `travel_minutes` to each food bank, and `drop_off` (`window`, `refrigerated`, `capacity_lb`, `food_bank_ids`) or `null`.
- **Food bank:** `food_bank_id`, `name`, `storage` (intervals with `cold_free_lb` and `dry_free_lb`), `pickup_windows`, `truck` (`window`, `refrigerated`, `capacity_lb`) or `null`, `travel_minutes_from_donor`, and `demand` as counts only: `households`, `people`, `below_fair_share_lb`, `limited_fridge`, `evening_only`.
- **Advocate:** `gaps`, one per food bank (`food_bank_id`, `name`, `households`, `below_fair_share_lb`, `low_access`), plus `declined`: items a food bank already countered down, so the advocate doesn't keep pushing them.

No facts ever name or describe an individual household.

### `turn`

`organization_id` (whose turn it is), `number`, `now` (the harness clock), and `accepted_by` (organizations whose accept stands on this version).

## Output: one move

```json
{"organization_id": "city", "version": 3, "action": "counter", "reason": "...", "amendment": {...}}
```

| `action` | Meaning | Carries |
|---|---|---|
| `accept` | This version works for my organization. Not an approval: my human still has to approve. | `reason` |
| `counter` | Change exactly one thing. Creates the next version, and old accepts stop counting. | `reason`, one `amendment` |
| `reject` | My organization won't take part on these terms. | `reason` |
| `request_hold` | Reserve my own resources for this version, until they expire. | `reason`, `resource_owner`, `holds` |
| `ask_human` | My organization's human must check something first, such as a condition doubt. | `reason` |
| `pass` | Take my turn with no change. | `reason` |

`pass` is the sixth move, added by Lane B and accepted by Lane C (README decision 6).

**Amendments** (exactly one per counter):

- `set_pounds`: `produce_id`, `food_bank_id`, `pounds` (0 removes the line).
- `shift_pounds`: `produce_id`, `from_food_bank_id`, `to_food_bank_id`, `pounds`.
- `set_transport`: `food_bank_id`, `mover`, `departs_at`, `arrives_at`.

**Holds**: each has `resource` (`lot`, `drop_off`, `storage_cold`, `storage_dry`, `truck`), `pounds` (or `null`), `start`, and `end`. The owner is always the organization making the move.

## Rules every move follows

- Every move names the version it's about and gives a non-empty reason.
- A counter carries exactly one amendment. Other moves carry none.
- The **advocate** may only `counter` or `pass`. It never accepts, rejects, holds, or asks a human (ADR 0001).
- An organization only holds its own resources.
- **No move commits anything.** A commitment needs every named organization's human to approve the exact same version, with valid holds (Lane A's protocol and the approvals API).
- Every number in a reason comes from the draft, the facts, or a calculator result (ADR 0002). The LLM negotiators (#13) are checked against this, with a template sentence after two failed checks.

## How Lane C carries it

Lane C's transport (PR #27) wraps this input in an envelope with `event_id` (the lot ID, README decision 7) and a `sequence` number, broadcasts it, and returns the move unchanged. The envelope adds ordering only. It never accepts or commits for anyone.
