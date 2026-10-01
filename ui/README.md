# agent-quiz report UI

React + TypeScript + Vite app for the `agent-quiz report` frontend.

The app reads one file, `data/report.json`, which holds the rows of the three
DuckDB tables (`results`, `agent_logs`, `tool_calls`). Row types are in
`src/data/types.ts`, and `src/data/load.ts` is the only module that fetches
data. Views go through it, so the data source can change later without
touching them (see `TODO.md`, "Report frontend: querying and sharing").

## Development

```sh
npm install
npm run dev      # dev server with hot reload
npm run lint
npm run build    # type-check + production build into dist/
```

`npm run dev` and `npm run build` expect report data at
`public/data/report.json` (gitignored). Generate it from a results database
before working on views.
