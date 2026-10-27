# Shared theme

`theme.css` is the one set of design tokens (`--hn-*`) and small shared parts (wordmark, buttons, cards,
pills, notes, form controls, focus ring) for every web app: `landing`, `household`, `donor-dashboard`
and `results-strip`. It is plain CSS with no build step of its own.

- **Look:** fresh greens, a berry accent, cold-chain blue, warm neutrals. Archivo for headings, IBM Plex
  Sans for body text (Google Fonts, with system fallbacks, so the pages still work on a slow line).
- **Light and dark:** follows `prefers-color-scheme`. A page can force a mode with
  `<html data-theme="light">` or `data-theme="dark"`. Header, hero and footer stay deep green in both.
- **Motion:** `prefers-reduced-motion` turns transitions and animations off.
- **Contrast:** every text pair meets WCAG AA (4.5:1) and UI parts meet 3:1. Check it with
  `python3 frontend/shared/check_contrast.py` after changing a color.

## Use it in an app

In the app's `src/styles.css`, after `@import "tailwindcss";`:

```css
@import "../../shared/theme.css";
```

In its `index.html`, the font links (the stylesheet loads without blocking the first paint):

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link rel="stylesheet" media="print" onload="this.media='all'" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..100,500..800&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" />
```

Every app's header shows the wordmark as a link to `/`:
`<a class="hn-wordmark" href="/"><Sprout aria-hidden="true" /><span>HarvestNet</span></a>`.
