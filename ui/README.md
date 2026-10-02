# honest-agent report UI

React + TypeScript + Vite app for the `honest-agent report` frontend.

The app reads one file, `data/report.json`, which holds the rows of the three
DuckDB tables (`results`, `agent_logs`, `tool_calls`). Row types are in
`src/data/types.ts`, and `src/data/load.ts` is the only module that fetches
data. Views go through it, so the data source can change later without
touching them (see `TODO.md`, "Report frontend: querying and sharing").
Components and tokens come from `src/ds/` (see its README).

## Development

```sh
npm install
npm run dev      # dev server with hot reload
npm run lint
npm run build    # type-check + build into ../cli/honest_agent/report_ui/
```

`npm run dev` serves `/data/*` from a report folder written by `honest-agent
report`, by default `../example_project/honest_agent_report` (run `honest-agent
report` in `example_project/` first). Point it elsewhere with
`HONEST_AGENT_REPORT_DIR=/path/to/report npm run dev`.

`npm run build` writes into the Python package, and that output is
committed: it's what `honest-agent report` copies next to the data, so pip
users never need Node. Rebuild and commit it whenever you change the UI.
