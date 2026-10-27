# Contributing

User docs live on the site, [thehonestagent.dev/docs](https://thehonestagent.dev/docs/).
This file is for working on honest-agent itself.

## The repository

| Folder | What it is | How to work on it |
|---|---|---|
| `cli/` | The `honest-agent` Python CLI | This file |
| `ui/` | The web report (React + Vite); its build is committed to `cli/honest_agent/report_ui/` | [`ui/README.md`](ui/README.md) |
| `site/` | The landing page and docs (Astro + Starlight) | [`site/README.md`](site/README.md) |
| `example_project/` | A demo project that uses `cli/` as an editable install | [`example_project/README.md`](example_project/README.md) |

## Setup

Python tooling is managed with [`uv`](https://docs.astral.sh/uv/) — never a
hand-rolled `venv`/`pip install`.

```bash
cd cli
uv sync --all-extras     # base deps + test + lint (Python >=3.10;
                          # uv picks a suitable interpreter, or pass --python 3.11)
uv run honest-agent --help
```

## Running tests

```bash
cd cli
uv run pytest -q
```

## Linting and formatting

Linting/formatting is [Ruff](https://docs.astral.sh/ruff/). Run it from
`cli/` against the whole repo:

```bash
cd cli
uv run ruff check ..            # lint
uv run ruff format ..           # format
uv run ruff format --check ..   # format, check only (what CI runs)
```

CI (`.github/workflows/ci.yml`) runs `pytest` across the supported Python
versions and `ruff check`/`ruff format --check` on every push and pull
request to `main`. Both must pass before a PR can be merged.

## Docs

- **One place per fact.** How-tos, guides and reference go on the site, in
  `site/src/content/docs/`. The README only pitches, shows a quickstart and
  links there; folder READMEs say how to build or run that folder.
- **Check claims against the code.** A docs page describes what the CLI does,
  so check it against the code and `--help`.
- **Regenerate the reference pages** after changing a command, an option or a
  config setting: `uv run --directory cli python ../site/scripts/generate_reference.py`
  from the repository root. CI fails if they're out of date.
- **Look at every screen size.** After changing the landing page, the docs
  layout or the report, check it at 1440px, 768px, 390px and 320px wide.

## How changes reach people

- **Merge a pull request once it's reviewed and CI passes.** `main` is the next
  version in progress: its notes go under "Unreleased" in `CHANGELOG.md`. Each
  version has a GitHub milestone, to track what goes into it.
- **People get changes only from a release.** The CLI is installed pinned to a
  tag (`…the_honest_agent.git@v0.3.1`), and the Docker image is built when a `v*`
  tag is pushed. So merging to `main` changes nothing for them.
- **The site is published from the `live` branch, not `main`.** Cloudflare Pages
  deploys `live` to https://thehonestagent.dev, so the docs match the latest
  release. It deploys `main` as a preview at its own URL, to check unreleased
  docs.
- **A site fix that can't wait for the release** (a typo, a landing-page tweak):
  merge it to `main` as usual, then copy it to `live`:
  `git checkout live && git cherry-pick <commit> && git push origin live`.
  Only for changes that are true of the released version.
- **Release small and often:** once a few changes have landed, cut a version.

## Releasing

1. Add the release's notes to `CHANGELOG.md`, breaking changes first.
2. Bump `version` in `cli/pyproject.toml`.
3. Check the prices in `cli/honest_agent/prices.py` against
   [Claude's](https://platform.claude.com/docs/en/about-claude/pricing) and
   [OpenAI's](https://developers.openai.com/api/docs/pricing) pricing pages, add new
   models, and set `PRICES_AS_OF` to the day you checked.
4. Replace the old tag (e.g. `v0.1.0`) everywhere users copy an install line:
   `grep -rn 'v0\.1\.0' --exclude-dir=node_modules --exclude-dir=.git .`
   (the README, Getting started, the CI recipe, the site footer).
5. Tag the release (`git tag -a v0.2.0`) and publish a GitHub Release.

Then publish the site for the release: `git push --force origin v0.2.0:live`
(`live` always points at the latest release, plus any site fixes copied there).

## Style

- SQL is written lowercase — keywords included (`select`, `from`, `where`,
  ...), everywhere SQL appears: seed scripts, tool implementations, storage
  code, docs.
- Name the provider (Anthropic, OpenAI) when something goes by the provider: defaults,
  API keys, prices ("the default for Anthropic agents"). Name the model family (Claude,
  GPT) only when it's about the models themselves.
