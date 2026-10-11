# HarvestNet

A mobile household frontend built with React, TypeScript, Tailwind CSS, and Vite.

## Run locally

Install Node.js 20.19+ (or 22.12+), then run:

```sh
npm install
npm run dev
```

Open the local URL printed by Vite. `npm run build` checks TypeScript and produces the production bundle; `npm run preview` serves that bundle.

## Household flow

Household details → answer review and explicit consent → food bank selection → pickup window and confirmation. English and Spanish are available throughout. The layout adapts to small phones and desktop browsers. No household name, home address, or income is collected.

`src/api.ts` is the placeholder backend adapter. Replace its methods with real API calls when the backend is available. Fair-share values come from that adapter, not a frontend calculation. All locations, distances, hours, pickup codes, credit amounts, confirmations, and cancellations are synthetic demo data. Nothing is booked or submitted to an external service. Answers exist only in memory and reset on reload.

The UI uses example credits from the supplied reference. The design document currently proposes fair share in pounds; the backend's published policy must establish the final unit before integration.
