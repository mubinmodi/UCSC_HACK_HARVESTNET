# Calculator interface

**Status: Agreed (team, October 11, 2026; recorded by Claude at the leader's direction).** Owner: Lane A (#8). Shared rules are in the [README](README.md).

**Calculators** are the specialists' deterministic tools. They are the only source of derived numbers (ADR 0002). Rules-based negotiators call them directly; LLM negotiators call them as tools with the same JSON. Every call is logged with its inputs and result, so the number check can trace each number in a message back to one.

Examples: [`examples/calculators.json`](examples/calculators.json), with inputs and outputs for every calculator below. They work as stand-ins: a lane that needs a calculator before Lane A's real one exists can return these. All numbers are synthetic, and fair-share pounds come from the placeholder table (`0.1.0-placeholder`).

This follows Lane B's stand-in `Calculators` interface (#11, `agents/src/harvestnet_agents/calculators.py`), plus the fair-share calculator already on `main` (`fair_share.py`) and one new calculator, `household_portions`. Lane A's real calculators should match it, and ticket #20 swaps them in.

## The six from ticket #1

| Calculator | Input | Output |
|---|---|---|
| `fair_share` | `household_size` | `pounds` per `period` (`week`), `unit`, `table_version`, `is_placeholder` |
| `household_portions` | `pounds_available` of one item at one food bank; `households` (`request_code`, `household_size`, `received_lb`) | `portions` (`request_code`, `pounds`, `fair_share_lb`, `still_below_lb`), `left_over_lb`, `table_version` |
| `proportional_split` (Proposed, ADR 0013) | `held_lb` and `gaps_lb`: pounds of one item each food bank holds, and each one's fair-share gap | `total_lb`, `shares_lb` (whole pounds, each at most its gap, in proportion to the gaps), `short_lb` (how far each holding is below its share), `unassigned_lb` |
| `storage_at` (storage over time) | `storage` intervals (`window`, `cold_free_lb`, `dry_free_lb`), and a time `at` | `cold_free_lb`, `dry_free_lb`, `recorded` |
| `pickup_feasibility` | `arrives_at`, the food bank's `pickup_windows`, the item's `usable_until` | `feasible`, `collect` window or `null`, `problem`, `last_pickup_end` |
| `to_pounds` (unit conversion) | `produce_id`, `quantity`, `unit`, `lb_per_unit` (the donor's stated pack weight, or `null`) | `pounds` |
| `fair_share_gap` | `households` (`household_size`, `received_lb`), as counts with no codes | `gap_lb`, `households`, `households_below`, `table_version` |

## Supporting calculators (already used by #11)

| Calculator | Input | Output |
|---|---|---|
| `capacity_fit` | `free_lb`, `needed_lb` | `fits`, `room_left_lb`, `over_by_lb` |
| `gap_after_plan` | `gap_lb`, `planned_lb` | `remaining_gap_lb`, `above_gap_lb` |
| `arrival_time` | `departs_at`, `travel_minutes` | `arrives_at` |

## Rules

- **Fair share** depends only on household size. SNAP is never an input.
- **Household portions** (new): give to the household furthest below its fair share first, evening out the pounds still owed, and never past anyone's fair share. Whatever is left is `left_over_lb`, which can still go out rather than waste. In the first example, 10 lb among households 12, 4, and 0 lb below gives 9, 1, and 0 lb, leaving each of the first two 3 lb below. Before calling it, the caller filters to households who can collect in time, who don't list the item as something they can't eat, and, for produce that needs a fridge, who either have fridge space or pick up the same day. Rounding is open: Lane A may round to 0.1 lb and add the remainder to `left_over_lb`.
- **Storage over time**: with no storage record for that moment, there is no space. Nothing is assumed.
- **Pickup feasibility** returns one of three problems when it fails: `no_pickup_hours`, `arrives_after_pickup_ends`, or `spoils_before_pickup`.
- **Unit conversion** never guesses a pack weight. A unit with no weight in the produce profile needs the donor's `lb_per_unit`, or the call fails.
- **Fair-share gap** takes counts only. It never sees request codes.

## Calling convention

As JSON (LLM tool calls, logs, and the examples file):

```json
{"calculator": "capacity_fit", "input": {"free_lb": 150, "needed_lb": 200}}
{"calculator": "capacity_fit", "output": {"fits": false, "room_left_lb": 0, "over_by_lb": 50}}
```

A calculator that can't answer from its inputs returns an error instead of an output:

```json
{"calculator": "to_pounds", "error": {"code": "calculator_error", "message": "no stated pounds per case for Apples; the donor must give it"}}
```

In Python, Lane B's `Calculators` protocol has one method per calculator with the same input names. It doesn't yet have `fair_share` (that's `fair_share.fair_share()` on `main`) or `household_portions`; Lane A adds both to the real interface. `to_pounds` returns a bare number and `arrival_time` a `datetime`; in JSON they're wrapped as `{"pounds": ...}` and `{"arrives_at": ...}`.
