# Project instructions

## SQL style

Write all SQL in lowercase — keywords included (`select`, `from`, `where`,
`group by`, `join`, etc.), not `SELECT`/`FROM`/`WHERE`. Applies everywhere
SQL is written: seed scripts, tool implementations, storage code, docs.

## Design system

`ui/src/ds/` is copied from the Claude Design project "The Honest Agent
Design System", which is the source of truth and holds files that exist only
there (guidelines, the `ui_kits/dashboard` screens, uploads). Never run the
full `/design-sync` conversion against it: it can overwrite or delete those
files. Sync with targeted file writes only — see `ui/src/ds/README.md` for
the rules and the sync steps.

## Site

`site/` is the landing page and the docs (Astro + Starlight; see
`site/README.md`). It uses `ui/src/ds/` only through its `@ds` alias, so a
design system change affects the site too. Keep `site/` self-contained (it may
move to its own repo): no relative links or imports outside it except `@ds`,
and docs link to code with full GitHub URLs. Check docs claims against the CLI
code and `--help`, not only the README.

## Check every screen size

After any change to the landing page or the generated report, look at it on
desktop (1440px), tablet (768px) and phone (390px and 320px) before calling
it done: take screenshots, check the layout, text wrapping and horizontal
scroll, and open interactive parts (tabs, collapsible sections, hovers) at
each size.

## Maintainer notes (Jose)

Jose keeps private project notes in his knowledge base: locally at
`~/knowledge/projects/the-honest-agent/`, or the private repo
`jlcoto/knowledge` in cloud sessions. If you can reach it, read the notes
there before bigger changes. The project's to-do list (`todo.md`) and
longer-term ideas (`future-ideas.md`) live there too, not in this repo. At the end of a session, suggest `/wrap-up`
to save decisions and learnings there. Contributors without access can
ignore this section.

## Merging and releasing

A PR is merged once it's reviewed and CI passes, not held for a release. The site
is published from the `live` branch (the latest release), not `main`, so merging
never changes what people see. Release steps and site fixes between releases: "How
changes reach people" and "Releasing" in `CONTRIBUTING.md`.
