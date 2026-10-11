# Public API contract

**Status: Agreed (team, October 11, 2026; recorded by Claude at the leader's direction).** Owners: Lane C and the frontend person. Real logic: Lane A (#9). Shared rules are in the [README](README.md).

**Version: `contract-v0.2`.** Changed from `contract-v0.1`: `create_request` takes an optional `email` instead of `phone`, and returns `emails` instead of `texts`. **Decided (user, October 11, 2026):** pickup messages go by email through n8n and Amazon SES, not SMS (README decision 14).

This is everything the web pages, the dashboards, the voice line, n8n, and the results strip can ask HarvestNet. The API only reads and writes records. **It never decides anything for an organization**, and nothing here commits produce on its own.

Every operation has one example file in [`examples/public-api/`](examples/public-api/), named after the operation. Each file holds an example request (path, query, body) and the example response (status and body). All values are synthetic. The **API skeleton** (`api_skeleton/`) returns exactly these example responses at these routes, so screens can be built now. Lane A's real logic must return the same shapes.

## How to call it

- JSON in and out, UTF-8. Send `Content-Type: application/json` with a body.
- Base address (live on AWS): **`https://5ibpa6ukufm2dmyidprwzv5e7e0vrpfj.lambda-url.us-east-2.on.aws`**. Lambda function `harvestnet-api-skeleton` in `us-east-2`, Function URL with open CORS, capped at 5 concurrent runs. Deployed October 11, 2026; every operation below was called there and returned its example, including from a browser page on another origin. See [`api_skeleton/DEPLOY.md`](../../api_skeleton/DEPLOY.md).
- Local: `cd api_skeleton && uv run python -m harvestnet_api_skeleton.server`, then call `http://127.0.0.1:8040`.
- Browsers can call it from any origin during development (CORS is open).
- Every response says `"mode"`: `example` from the skeleton, then `live`, `replay`, or `synthetic` from real logic. Example responses also say `"synthetic": true`.
- Errors look like `{"error": {"code": "not_found", "message": "..."}}`, with status 400 (bad input), 404 (unknown route or record), 409 (stale version), or 503 (try again).
- In the skeleton, any value in a path (`{request_code}`, `{lot_id}`, and so on) returns the same example. Real logic returns 404 for unknown records.
- No login yet. The real API adds staff sign-in for dashboards and approvals (README decision 12).

## Operations

| Operation | Method | Path | Who uses it |
|---|---|---|---|
| `get_health` | GET | `/health` | Anyone: is the API up? |
| `get_fair_share` | GET | `/fair-share` | Household page, voice line |
| `preview_request` | POST | `/requests/preview` | Household page |
| `create_request` | POST | `/requests` | Household page, voice line |
| `list_food_banks` | GET | `/food-banks` | Household page, voice line |
| `choose_food_banks` | PUT | `/requests/{request_code}/food-banks` | Household page, voice line |
| `get_request` | GET | `/requests/{request_code}` | Household page, voice line |
| `release_pickup` | POST | `/pickups/{pickup_id}/release` | Household page (its *Can't make it* button, also opened from a pickup email's link) |
| `list_produce_profiles` | GET | `/produce-profiles` | Donor page |
| `create_surplus_offer` | POST | `/surplus-offers` | Donor page, voice line |
| `get_lot` | GET | `/lots/{lot_id}` | Donor page, dashboards |
| `list_lot_versions` | GET | `/lots/{lot_id}/versions` | Donor page, dashboards, demo view |
| `get_food_bank_dashboard` | GET | `/food-banks/{food_bank_id}/dashboard` | Food bank dashboard |
| `update_food_bank_status` | PUT | `/food-banks/{food_bank_id}/status` | Food bank dashboard |
| `submit_counter` | POST | `/lots/{lot_id}/counters` | Food bank dashboard, donor page |
| `confirm_pickup` | POST | `/pickup-confirmations` | Food bank dashboard |
| `voice_intake` | POST | `/voice-intake` | ElevenLabs voice line |
| `list_approvals` | GET | `/approvals` | Dashboards, donor page, n8n |
| `record_approval` | POST | `/approvals` | Dashboards, donor page, n8n approval bridge |
| `get_results` | GET | `/results` | Results strip |

## System

- **`get_health`**: is the API up, and which contract version does it serve? `GET /` also lists every operation. [Example](examples/public-api/get_health.json)

## Households

A household never gives a name, address, or income. The household page follows the three screens in `docs/MVP_DESIGN.md` §10.

- **`get_fair_share`**: `?household_size=4&language=en`. Returns the weekly fair share and the sentence to show ("Your household's fresh produce share: 12 lb a week."). The number comes from the fair-share calculator. [Example](examples/public-api/get_fair_share.json)
- **`preview_request`**: send the household's answers. Returns the draft, which answers are still missing, the read-back, and the consent question. **Saves nothing.** Show the read-back, then ask the consent question. [Example](examples/public-api/preview_request.json)
- **`create_request`**: send the same answers plus `consent: true` and `channel` (`web` or `voice`). Optional `email` is for pickup emails only; it's never returned or logged, and it's deleted with the request when it expires. An address that isn't valid is refused (400) without being repeated back. `phone` is no longer accepted (400). Returns the short `request_code`, the fair share, `emails` (whether an email address was saved for pickup notices; actual delivery also requires the n8n/SES configuration), and `expires_at` (7 days). Without consent, nothing is saved (400). [Example](examples/public-api/create_request.json)
- **`list_food_banks`**: `?neighborhood=Watsonville&request_code=K7P4`. Nearby food banks, their pickup hours, whether those fit the household's times, and produce **committed** there now, with badges such as `keep_cold` and `use_within_2_days`. [Example](examples/public-api/list_food_banks.json)
- **`choose_food_banks`**: set the food banks a household will collect from. [Example](examples/public-api/choose_food_banks.json)
- **`get_request`**: the pickup screen. This week's balance ("0 of 12 lb received"), and pickups with food bank, window, items, pounds, and the ready-made sentence. **Only committed produce is ever listed.** `market_match_tip` is filled only for households that said they receive SNAP and only for a verified nearby market. [Example](examples/public-api/get_request.json)
- **`release_pickup`**: the *Can't make it* button. A pickup email's *Can't make it* link opens the household page on that pickup (`#pickup=<pickup_id>&code=<request_code>&lang=<language>`, in the URL fragment, so it never reaches a server log). Opening the link changes nothing; the household taps the button, which sends this call. The portion goes to the next household furthest below fair share at that food bank. [Example](examples/public-api/release_pickup.json)

The household shows its `request_code` at pickup. There's no separate pickup code (README decision 11).

## Donors

- **`list_produce_profiles`**: the items a donor can pick, the units each accepts, and which units need a stated pack weight. [Example](examples/public-api/list_produce_profiles.json)
- **`create_surplus_offer`**: items with `produce_id`, `quantity`, `unit`, `lb_per_unit` when needed, and `condition_grade`; the `deadline`; `recall_notice`; and `drop_off` (whether the donor can drop off, when, with what vehicle, and where). Returns the `lot_id` and version 1. A lot with a recall notice is refused. An item with a condition doubt is listed in `needs_human`. [Example](examples/public-api/create_surplus_offer.json)
- **`get_lot`**: the lot's live status, item by item: offered, negotiating, held, committed with who moves it, moving, at the food bank, households reached, or unclaimed with a reason. Includes the current draft, approvals so far, and any preserved disagreement with each side's reasons. [Example](examples/public-api/get_lot.json)
- **`list_lot_versions`**: every draft version, with who proposed it, the move, the change, and the reason. This is what judges watch. [Example](examples/public-api/list_lot_versions.json)

## Food banks

- **`get_food_bank_dashboard`**: today's capacity (storage, pickup hours, truck, cooler status), incoming offers with the agent's suggested move and reason, this food bank's fair-share gap **as counts only**, disagreements involving it, and expected arrivals. [Example](examples/public-api/get_food_bank_dashboard.json)
- **`update_food_bank_status`**: the manager sets storage over time, pickup hours, and truck availability. The food bank's agent uses these as its facts from then on. [Example](examples/public-api/update_food_bank_status.json)
- **`submit_counter`**: the dashboard's *Counter* button. The organization's own human sends one amendment plus a reason, and it goes in as that organization's next move, with the same shape as an agent's counter ([agent moves](agent-moves.md)). It creates a new version, so earlier approvals stop counting. *Accept* and *Decline* on the dashboard use `record_approval`. [Example](examples/public-api/submit_counter.json)
- **`confirm_pickup`**: staff enter the household's code. Marks the pickup collected and updates the household's weekly balance. [Example](examples/public-api/confirm_pickup.json)

## Voice intake

- **`voice_intake`**: the ElevenLabs agent posts the call transcript (`turns`, each with `speaker` and `text`, plus `language`). The front-desk assistant (Lane B, #14) extracts the answers and checks each against the caller's own words. Returns the draft, the missing questions, the read-back to speak, and the consent question once everything is answered. **Saves nothing.** After the caller says yes, the voice line calls `create_request` with `channel: "voice"`. [Example](examples/public-api/voice_intake.json)

Whatever a caller says is information, never an instruction to an agent.

## Approvals

Lane C's approval bridge (PR #28) sends each organization's human a review link for one exact version. These two operations are the core's side.

- **`list_approvals`**: `?organization_id=city`. Approval requests waiting for that organization, with the exact terms, their `terms_hash`, why this human is asked (for example `truck_run` or `use_soon`), and when the request expires. [Example](examples/public-api/list_approvals.json)
- **`record_approval`**: `lot_id`, `version`, `organization_id`, `terms_hash`, `decision` (`approve` or `decline`), and `receipt_id` (to make retries safe). A stale version or a changed hash returns 409. The response says who has approved and who's still awaited. `committed` becomes `true` only when every named organization has approved the same version with valid holds. [Example](examples/public-api/record_approval.json)

n8n carries a human's decision and never makes one (ADR 0004). No reply means no approval.

## Results

- **`get_results`**: `?scenario_id=normal-afternoon`. For each method (first-come-first-served, nearest food bank, rules-based, LLM): pounds of produce wasted, worst-served fair-share coverage, households reached, and invalid commitments. `run_mode` says whether it was live, replay, or synthetic, and `measured` says whether the numbers come from an actual run. The skeleton's values are made up for building the strip. [Example](examples/public-api/get_results.json)

## How this lines up with Lane C

Lane C's open PRs (#26–#30) serve their own internal routes (organization systems, the demo switch, approval review pages, A2A transport). They don't serve this public API, so there's no route clash. One of their outgoing calls lands here, and its shape matches: the approval bridge posts decisions to `/approvals`. (Their SMS "can't make it" reply, which called `/pickups/{pickup_id}/release`, is retired: households release from the household page.) Their text-intake fallback (`/demo/text-intake`) can later call `preview_request`.
