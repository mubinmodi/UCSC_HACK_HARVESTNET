# Scenario fixture format

**Status: Agreed (team, October 11, 2026; recorded by Claude at the leader's direction).** Owner: Lane A (#7). Shared rules are in the [README](README.md).

A **scenario fixture** is one scripted day, in one JSON file. The scenario harness runs it through any negotiation method (first-come-first-served, nearest food bank, rules-based, or LLM) and outputs the event log, the outcomes, and the rule-check results. Every method gets the same file.

Example: [`examples/scenario-normal-afternoon.json`](examples/scenario-normal-afternoon.json). It's a normal afternoon: eight households, a farmers market's mixed surplus lot (300 lb apples, 200 lb romaine, 8 sacks of potatoes at 50 lb each), three food banks, and the city food bank's cooler failing at 3:30 pm. All of it is synthetic.

## Top-level fields

| Field | Meaning |
|---|---|
| `kind` | Always `"scenario"`. |
| `contract_version` | `"contract-v0.1"`. |
| `synthetic` | `true` for any made-up scenario. Recorded live data would say `false` and give its source. |
| `scenario_id`, `title` | Short ID and a plain name. |
| `note` | A plain sentence saying what's synthetic or where the data came from. |
| `mode` | `synthetic`, `replay`, or `live`. Results carry it forward, so judges know what they're seeing. |
| `timezone` | The region's time zone. Every timestamp still carries its own offset. |
| `clock` | `start` and `end` of the scripted day. The harness owns the clock; no agent reads the wall clock. |
| `policies` | Versions of the fair-share table and produce profiles to use, the stop rule (rounds without new terms), and request expiry in days. |
| `organizations` | Every participant: `organization_id`, `role` (`donor`, `food_bank`, `advocate`), and display `name`. |
| `turn_order` | The published order of turns. The harness schedules turns; it never decides for anyone. |
| `donors` | Each donor's own facts: travel minutes to each food bank, and its drop-off ability (window, refrigerated or not, capacity, food banks on its routes). `drop_off` is `null` when it can't deliver. |
| `food_banks` | Each food bank's own facts: area, `low_access` (USDA Food Access Research Atlas context), storage over time (`cold_free_lb`, `dry_free_lb` per interval), dated pickup windows, and its truck (or `null`). |
| `travel_minutes_between_food_banks` | Recorded travel times, used when produce moves after a cooler failure. |
| `requests` | Households' requests. No names, addresses, or phone numbers. See below. |
| `surplus_offers` | Each donor's surplus lot. See below. |
| `faults` | Timed problems, such as a cooler failure. |
| `humans` | Scripted human decisions, standing in for each organization's staff. |
| `household_replies` | How each household answers its pickup notice. |
| `rule_checks` | The checks to run. Every run checks all of them. |

There's no `expected` split. The split follows the run (ADR 0005). A test may add its own expectations next to a fixture, but the fixture never prescribes a winner.

## Requests

One entry per household, with the fields from the Request record (`docs/MVP_DESIGN.md` §11):

- `request_code`: short code, never a name.
- `submitted_at`, `channel` (`web` or `voice`), `language` (`en` or `es`).
- `household_size`, which sets the fair share through the fair-share calculator. The fair share itself is not stored in the fixture.
- `received_this_week_lb`: produce already received this week.
- `pickup_windows`: weekly, as `days` plus local `start` and `end` (`"18:00"`). `end: null` means open-ended ("after 6 pm").
- `limited_fridge`, `neighborhood`, `cant_eat` (a list of produce IDs or plain words).
- `snap`: `yes`, `no`, or `not_said`. It never changes the fair share. Agents see it only as counts.
- `chosen_food_bank_ids` and `consent` (always `true`; a request without consent isn't saved).

Agents never see this list. Each food bank's specialists turn it into counts (households, people, limited-fridge count, evening-only count, pounds below fair share), and the advocate sees the same counts for every food bank.

## Surplus offers

- `lot_id`, `donor_id`, `reported_at`, and `deadline` (when the produce must leave the donor).
- `recall_notice`: `true` means the lot is never offered.
- `items`: one line per produce item. `produce_id` names its profile. `quantity` and `unit` are what the donor reported; `lb_per_unit` is the donor's stated pack weight when the profile has none. The unit calculator turns these into pounds. `condition_grade` is `good`, `use_soon`, or `not_for_people`. `usable_until` comes from the donor's condition check. `condition_doubt` (for example `"cold chain unknown"`) sends the item to a human first.

## Faults

Each fault has `at`, `kind`, the affected organization, a `reading`, a `source`, and `synthetic: true`. The MVP has one kind, `cooler_failure`: the food bank's cold space drops to zero from that moment. Lane C's Beeceptor switch produces the same reading in the live system.

## Humans and household replies

- `humans`: for each organization, what its human does when asked to approve (`approve` or `decline`) and after how many minutes. This is a script standing in for a person, labeled as such in results. It is not an automatic commitment: the harness still records one approval per organization per exact version, and commitment still needs all of them.
- `household_replies`: `collect`, `cant_make_it` (the portion is released to the next household furthest below fair share), or `no_reply`.

## Rule checks

From the spec's Seam 1. Every run reports each as pass or fail:

- `zero_invalid_commitments`
- `no_double_booking` (storage, trucks, produce)
- `pounds_conserved` per item across custody changes
- `fair_share_respected`: no household above its fair share while another at the same food bank is below it
- `versioned_approvals`: every approval tied to the current version
- `no_auto_commit`, including at the deadline
- `all_pounds_have_pathway`
- `number_check_failures_counted`

Lane C's join (`docs/platform/JOIN.md`, PR #30) already expects these as boolean keys, under the same names for the six it lists.
