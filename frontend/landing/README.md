# HarvestNet landing page

The site root (`/`). It explains the project (the problem, how it works, features, who it is for), has a
"Log in" button that opens a chooser, and links to the other apps. Vite, React and TypeScript, themed by
[`../shared/theme.css`](../shared/theme.css). English and Spanish.

- **Log in:** HarvestNet has no user accounts. The chooser sends a household to `/household/` (no account
  needed), donor or food bank staff to `/donor-dashboard/` (they sign in there with their organization's
  staff token, in Settings), and anyone who wants to look to `/results-strip/`. It is a dialog with a
  focus trap, closes on Escape, and returns focus to the button.
- **Honesty (ADR 0002):** no invented figures. The only numbers come from `GET /api/results` and appear in a
  panel labeled synthetic; if the call fails the panel is left out.
- **No personal data:** the footer lists the team's GitHub handles and the repository link, never emails.

```bash
npm ci
npm run typecheck && npm test && npm run build
npm run preview        # http://localhost:4173
```

`deploy/aws/setup.sh` builds this app with `--base=/` and the gateway (Caddy) serves it at `/`, after the
`/api/`, `/platform/`, `/human/`, `/systems/demo/*` and `/<app>/` routes. `VITE_API_BASE_URL` is optional;
without it the page calls `/api` on its own origin ([`.env.example`](.env.example)).

## Photo credit

The hero image `public/hero-produce-market.webp` (2000 x 1328, WebP, 226 KB) is
"assorted vegetables on green plastic crate" by Ashley Winkler
([@firlefanzski](https://unsplash.com/@firlefanzski)) on Unsplash:
<https://unsplash.com/photos/53f1vbOG7y8>. Unsplash License: free to use, including commercially, with no
permission needed; credit is not required but is given here and in the page footer. Source and license
checked on the photo's Unsplash page on 2026-10-27. The file is a WebP copy of that photo.
