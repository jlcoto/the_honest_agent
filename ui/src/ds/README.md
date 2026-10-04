# Design system (vendored)

Copied from the Claude Design project **The Honest Agent Design System**
(`94963a67-cb9a-4a54-9fcf-5068be36c5dc`) on 2026-10-01. The project's
`readme.md` holds the full guidelines (palette roles, accuracy buckets, type,
voice); follow it when building views.

- `styles.css` + `tokens/`: tokens as CSS variables, imported once in `main.tsx`.
- `components/`: the components, copied **unchanged**, each `.jsx` with its
  `.d.ts`. Don't edit them here. Change the design in Claude Design and copy
  again, so updates stay a clean diff. Import them from `./ds` (`index.ts`).
- Local change not yet in Claude Design: light-mode `--chart-empty` in
  `tokens/colors.css` is `#E2DFD5` (was `#ECEAE2`, the same as `--bg-sunken`,
  so empty bar tracks vanished on hovered table rows). The neutral `Badge`
  (`components/core/Badge.jsx`) also got a 1px `--border-1` inset ring, since
  its `--bg-sunken` fill vanished on hovered rows too. Push both in the next sync.
- `globals.d.ts` and `allowUmdGlobalAccess` in `tsconfig.app.json` exist only
  so the copied `.d.ts` files type-check under React 19.

Not copied: the `ui_kits/dashboard` reference screens, guideline cards, and
`assets/logo-mark.png` (`Logo` needs it; copy it into `public/` before using
`Logo`).

External requests at view time: fonts load from Google Fonts
(`fonts.gstatic.com`) and icons from unpkg (`lucide-static@0.469.0`). Offline,
text falls back to system fonts and icons don't render.
