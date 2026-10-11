# HarvestNet results strip (ticket #5)

React + TypeScript + Tailwind CSS + Vite, the same stack and setup as the household page (#2).
It's the demo's scoreboard: for one scenario, the four methods side by side (first-come-first-served,
nearest food bank, rules-based negotiators, LLM negotiators), with produce wasted, worst-served
fair-share coverage, households reached, and each run's mode label (live, replay, or synthetic).
English and Spanish.

## Run locally

Install Node.js 20.19+ (or 22.12+), then:

```sh
cd frontend/results-strip
npm install
npm run dev
```

Open the local URL Vite prints (usually http://localhost:5173). `npm run build` checks TypeScript and
creates the production bundle; `npm run preview` serves it. `npm run typecheck` and `npm test` run on
their own.

## Data

- `src/api.ts` is the adapter for `GET /results?scenario_id=normal-afternoon`, as described in
  `docs/contracts/public-api.md` (on `main`).
- **No API address set (default):** the page shows the contract's example response
  (`docs/contracts/examples/public-api/get_results.json`). It's synthetic, so the page shows an
  "Example data" banner.
- **Real API:** start it with `VITE_API_BASE_URL=http://127.0.0.1:8050 npm run dev`. The API must allow
  this page's origin for CORS (the core server reads `HARVESTNET_ALLOWED_ORIGIN`). The deployed skeleton
  (`https://5ibpa6ukufm2dmyidprwzv5e7e0vrpfj.lambda-url.us-east-2.on.aws`) serves the same synthetic example.
- **The page calculates nothing.** It shows the API's numbers as sent. The only formatting is showing
  coverage (sent as a share, such as 0.25) as a percent. A missing number shows "Not measured yet", and
  a method the API marks `not_run` shows "Not run" with the API's reason.
- **Produce wasted** follows design section 16 (decided by the user October 11, 2026): pounds with no
  pathway at the scenario end. Under it, each card shows where every pound went, as the API sent it:
  collected by households, committed to food banks, wasted. Then, in small type, the earlier measure
  (not collected by the scenario's households). `src/split.ts` holds these labels and the legend in
  English and Spanish; `npm test` checks them. If an older API omits the new split, the page leaves
  the new waste measure unavailable and labels the old `produce_wasted_lb` as the earlier measure.
  Pounds are shown with at most one decimal.
- The banner appears whenever the API says `measured: false` or `synthetic: true`.
- Each card also follows its own method's `status` and `measured` (the evaluation runner's labels,
  `docs/core/README.md` #24), because a response can be `measured: true` while one method isn't:
  `fallback_only` shows "Fallback only · not an LLM result" and a dashed border, `partial` shows
  "Partial" with the API's reason, `not_run` shows no numbers, and a method with `measured: false`
  says "Not a measured result". `src/labels.ts` decides this; `npm test` checks it.

## Done-when checklist (from ticket #5)

- [x] Shows all four methods side by side for one scenario.
- [x] Clearly shows each run's mode label.
- [x] Numbers come only from the API. Nothing is calculated in the page.
- [ ] Readable on a projector. *(Large type, high contrast, and fits a 1920×1080 screen. Check on the real projector.)*
