// The only place the app gets data from. Views import from here, never fetch
// directly, so swapping the source (a `serve` query API, DuckDB-WASM) later
// only touches this module -- see TODO.md "Report frontend: querying and sharing".

import type { ReportData } from './types'

// Relative so the report works from any path it's hosted under.
const REPORT_DATA_URL = './data/report.json'

export async function loadReportData(): Promise<ReportData> {
  const response = await fetch(REPORT_DATA_URL)
  if (!response.ok) {
    throw new Error(`Couldn't load ${REPORT_DATA_URL} (HTTP ${response.status}).`)
  }
  return (await response.json()) as ReportData
}
