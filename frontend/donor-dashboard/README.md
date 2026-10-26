# Donor page and food bank dashboard (ticket #3)

React + TypeScript + Tailwind CSS (Vite). Built on the agreed public API contract (`docs/contracts/public-api.md`). Started by Gianellerella; connected to the API by Claude at the team lead's direction.

## Run

Node.js 20.19+ or 22.12+.

```sh
cd frontend/donor-dashboard
npm ci
npm run dev        # http://localhost:5173
npm run typecheck
npm run build
npm test           # Vitest + Testing Library; fetch is mocked, no network
```

The API address comes from `VITE_API_BASE_URL` (see `.env.example`). By default the app calls `/api` on its own origin, which is where the gateway serves the core. To develop against the example API skeleton, `https://5ibpa6ukufm2dmyidprwzv5e7e0vrpfj.lambda-url.us-east-2.on.aws` (it answers every operation with the contract's example response), set `VITE_API_BASE_URL` to it. For the core (`python -m harvestnet_core.server`, port 8050), set `VITE_API_BASE_URL=http://127.0.0.1:8050` and set `HARVESTNET_ALLOWED_ORIGIN` on the core to this page's origin.

## Screens

- **Report surplus** (donor): items from `GET /produce-profiles`, quantity and a unit the profile accepts, pack weight when the profile needs one, condition grade, deadline, recall notice (a recalled lot can't be sent), and drop-off ability with time, vehicle, and the food banks named by `GET /food-banks`. Sends `POST /surplus-offers`.
- **My lots** (donor): `GET /lots/{lot_id}` item by item (status, who moves each part, households reached, unclaimed with reason, approvals so far, preserved disagreement) and `GET /lots/{lot_id}/versions` (who proposed each version, the move, the change, and the reason). Condition checks appear for items with a condition doubt.
- **Dashboard** (food bank): `GET /food-banks/{id}/dashboard`. Today's capacity (storage, pickup hours, truck, cooler), fair-share gap as counts only, incoming offers with the agent's suggested move and reason, disagreements with each side's latest reason, expected arrivals, and pickup-code entry (`POST /pickup-confirmations`). *Update storage, hours, truck* sends `PUT /food-banks/{id}/status`.
  - **Accept / Decline** use `record_approval` with the `terms_hash` from `GET /approvals` for that exact version. Both need a click and a confirmation. If no approval request matches the offer's version, the buttons don't appear.
  - **Counter** sends one amendment (`set_pounds` or `set_transport`) and a required reason to `POST /lots/{lot_id}/counters`.
  - **Condition check**: approve as "use today" (`use_soon`) or decline (`not_for_people`) with a reason. It uses the core's proposed `POST /lots/{lot_id}/condition-checks` (docs/core/README.md, #9), which is not in the agreed contract yet. The skeleton answers 404, and the page says so.
  - **Disruptions**: when the dashboard response has `disruptions` (the core's #23 cooler-failure join), each one shows what must move and what can stay, a **reason card for every candidate food bank** (chosen and rejected, each with its reasons), the fallback, the flags to check, and who must give fresh approval. The skeleton's example has no `disruptions`, so the section is hidden there. The tests use a dashboard recorded from the core's cooler-failure join (`src/test/fixtures/dashboard-cooler-failure.json`, synthetic).
- **Approvals** (donor or food bank): `GET /approvals?organization_id=…`, with the exact terms and an explicit approve or decline of that version. Nothing approves on its own; no reply means no approval.
- **Settings**: which donor and food bank you work for, and your staff token.

## Staff sign-in

The core needs a different Bearer staff token for each organization on staff routes. Staff type it into Settings at runtime. It's kept in memory and `sessionStorage` for this tab only (never `localStorage`, a URL, a file, or a log), and sent only as the `Authorization` header to that organization's own staff calls. The skeleton has no sign-in, so it works without a token.

## Data rules

- Every number on screen comes from an API response (ADR 0002). The app computes no quantities.
- Each section shows the response's own `mode`/`synthetic` label: example, synthetic, replay, or live.
- Households appear only as counts. Pickup confirmation shows the request code and pounds, never a name.
- The default organization IDs (`market`, `city`) are the contract's example IDs.

## Tests

`src/api.test.ts` checks every call against `docs/contracts/examples/public-api/*.json` (method, path, query, body, and the response passed through), plus token handling. `src/App.test.tsx` drives the screens with fetch mocked from those same examples.

## Produce pictures

`public/produce/*.svg` were added on the original branch by Gianellerella. Each is a small SVG that draws emoji characters on a gradient, so how they look depends on the viewer's emoji font. Items without a picture show a leaf icon.
