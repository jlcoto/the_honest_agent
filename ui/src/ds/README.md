# Design system (vendored)

Copied from the Claude Design project **The Honest Agent Design System**
(`94963a67-cb9a-4a54-9fcf-5068be36c5dc`) on 2026-10-01; `tokens/colors.css` and
`components/core/Badge.jsx` updated in both places on 2026-10-04, and the
series palette (`--series-1…5`), `TrendChart` and the quiz → eval rename in
`Heatmap` on 2026-10-05; `Badge`'s `size="sm"`, the dashboard kit's result
page (`ui_kits/dashboard/Detail.jsx`, ported from `src/views/ResultDetail.tsx`)
and the kit's quiz → eval rename on 2026-10-07; bundled fonts (`tokens/fonts/`) and
icons (`components/core/icons.js`, used by `Icon`) on 2026-10-08. The project's `readme.md` holds the full guidelines
(palette roles, accuracy buckets, type, voice); follow it when building views.

- `styles.css` + `tokens/`: tokens as CSS variables, imported once in `main.tsx`.
- `components/`: the components, copied **unchanged**, each `.jsx` with its
  `.d.ts`. Don't edit them here. Change the design in Claude Design and copy
  again, so updates stay a clean diff. Import them from `./ds` (`index.ts`).
- `globals.d.ts` and `allowUmdGlobalAccess` in `tsconfig.app.json` exist only
  so the copied `.d.ts` files type-check under React 19.

## Where changes go

Claude Design holds the guidelines (`readme.md`) and the `ui_kits/dashboard`
screens; this folder holds a copy of the tokens and components the report is
built from; `src/views/` holds the real screens.

- **Tokens and components:** change them in Claude Design, then copy them here.
- **Screens:** design them in Claude Design, or mock them as artifacts when real
  data matters (as the result page's Trace did). Either way, check them against
  the guidelines before building, and after merging update the matching kit
  screen in Claude Design so it shows the product as it is.

## Syncing with Claude Design

The Claude Design project holds files that exist only there, so never run the
full `/design-sync` conversion (it rebuilds a project from a repo, replacing
or deleting what's there). Use targeted `DesignSync` writes instead, once per
finished redesign rather than per tweak:

1. `get_file` every remote file you'll touch and compare it with the copy
   here, so you start from what's really there.
2. Edit copies in a scratch folder. For `ui_kits/dashboard` screens, test
   locally first: build `src/ds/index.ts` with Vite in lib mode as an IIFE
   named `TheHonestAgentDesignSystem_94963a` (React as the global `React`,
   plus a small `ReactJSXRuntime` shim), and load the screen with fake
   `HA_DATA`.
3. `finalize_plan` with the exact paths and no deletes.
4. Write `_ds_needs_recompile`, then the files, then `_ds_needs_recompile`
   again. Claude Design rebuilds `_ds_bundle.js` from the component sources;
   never edit the bundle directly.
5. Update this README's copy date, and the screens (`ui_kits/dashboard`) when
   a view's design changed.

Not copied: the `ui_kits/dashboard` reference screens, guideline cards, and
`assets/logo-mark.png` (`Logo` needs it; copy it into `public/` before using
`Logo`).

No external requests at view time: the fonts (`tokens/fonts/`, SIL OFL 1.1) and
the icons the report uses (`components/core/icons.js`, Lucide, ISC) are bundled,
so the built report can ship a strict Content-Security-Policy (`vite.config.ts`).
`Icon` falls back to unpkg (`lucide-static@0.469.0`) for any other name, which
that policy blocks: add an icon to `icons.js` before using it in the report.
The licences are copied to `public/licenses/`, so they ship with the report.
