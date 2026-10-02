# Contributing

## Setup

Python tooling is managed with [`uv`](https://docs.astral.sh/uv/) — never a
hand-rolled `venv`/`pip install`.

```bash
cd cli
uv sync --all-extras     # base deps + test + lint (Python >=3.10;
                          # uv picks a suitable interpreter, or pass --python 3.11)
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

## Style

- SQL is written lowercase — keywords included (`select`, `from`, `where`,
  ...), everywhere SQL appears: seed scripts, tool implementations, storage
  code, docs.
- See `README.md` for the project layout (`cli/` vs. `example_project/`).
