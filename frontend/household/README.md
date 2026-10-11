# HarvestNet household page (ticket #2)

React + TypeScript + Tailwind CSS + Vite. The mobile web page a household uses to ask for fresh
produce, in English and Spanish, following the three screens in `docs/MVP_DESIGN.md` §10:

1. **About your household.** Household size (the page shows the fair share the API sends), pickup days
   and time, limited fridge space, neighborhood, anything it can't eat, an optional SNAP/CalFresh
   question (Yes / No / Prefer not to say), language, and an optional phone number for texts. Then a
   read-back and the consent question. Nothing is saved until the household says yes.
2. **Choose your food banks.** Nearby food banks, their pickup hours, whether those fit, and the produce
   committed there now, with badges such as *Keep cold*.
3. **Your pickup.** The request code (shown at pickup; there's no separate pickup code), this week's
   balance, committed pickups only, and a *Can't make it* button.

It never asks for a name, address, income, or immigration status, and stores nothing in the browser:
answers live in memory for the visit, and the phone number is dropped once it's sent.

## Run locally

Node.js 20.19+ or 22.12+:

```sh
cd frontend/household
npm ci
npm run dev        # http://localhost:5173
npm run typecheck
npm test           # Vitest + Testing Library, no network
npm run build      # type-checks, then builds dist/
```

## API

- The address comes from `VITE_API_BASE_URL` (see `.env.example`). Unset, the page calls the live API
  skeleton, `https://5ibpa6ukufm2dmyidprwzv5e7e0vrpfj.lambda-url.us-east-2.on.aws`.
- `src/api.ts` is the only place that talks to the API. It uses the household operations in
  `docs/contracts/public-api.md` with their exact shapes: `get_fair_share`, `preview_request`,
  `create_request`, `list_food_banks`, `choose_food_banks`, `get_request`, `release_pickup`.
- **The page calculates nothing.** The fair share, balance, pounds, read-back, consent question, and
  pickup sentence are shown as the API sends them (ADR-0002). The page only formats dates.
- **Example data is labelled.** The skeleton answers every call with the contract's synthetic example,
  whatever was entered (so its read-back says "4 people, Watsonville" for everyone). Whenever a reply
  says `"mode": "example"` or `"synthetic": true`, the page shows an *Example data* notice, and the
  read-back is marked as an example reply.
- Errors (`{"error": {"code", "message"}}`, timeouts after 20 s, no connection) show a plain message
  and *Try again*.
- When Lane A's real logic replaces the skeleton behind the same routes, the page needs no changes.

## Tests

`src/test/contract.ts` reads the contract examples from `docs/contracts/examples/public-api/` and mocks
`fetch` with them, the way the skeleton answers. The tests check that every call the page makes matches
a contract example's method, path, query, and body; that nothing is saved without consent; that only
committed pickups appear; that the fair share is shown as sent; and that no name, address, or income
question exists.
