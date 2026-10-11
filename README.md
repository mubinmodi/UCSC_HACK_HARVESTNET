# HarvestNet organization workspace

React + TypeScript + Tailwind CSS frontend for donor staff and food bank managers. Based on the supplied mobile reference, with a sidebar and wider workspace on desktop.

## Run

Install Node.js 20.19+ or 22.12+, then:

```sh
npm install
npm run dev
```

`npm run build` checks TypeScript and creates a production bundle. `npm run preview` serves it locally.

## Screens

- Report surplus produce: profile selector, quantity/unit, condition, deadline, recall flag, delivery ability, and notes.
- My Donations: active/completed filters, item status, transport information, household reach, and relisting with a new deadline.
- Food Bank Dashboard: storage, truck/cooler status, pickup hours, fair-share gap, and incoming offers.
- Offer Details: example recommendation, accept/counter/decline, arrival condition checks, pickup code validation, and preserved reasons.
- Messages, inventory, and distribution views are accessible through navigation.

All data and actions are **synthetic examples**. `src/api.ts` contains the replaceable in-memory API adapter. No external offers or approvals are created. Reloading resets state. Approval by one organization does not create a commitment; all organizations must approve the same draft in the real backend. The sample pickup code for committed lettuce is `7316`; approve the arrival condition first. Each offer detail shows its example code.

Produce thumbnails are bundled SVG illustrations and require no external image requests. Resource and fair-share values come from the API adapter. Frontend validation is only for this demo; the backend must validate food safety, capacity, draft versions, and all commitments during integration.
