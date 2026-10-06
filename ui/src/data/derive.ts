import type { ReportData, ResultRow, ToolCallRow } from './types'

export interface Run {
  run_id: string
  /** "YYYY-MM-DD HH:MM" */
  timestamp: string
  date: string
  agent: string
  model: string
  results: ResultRow[]
  accuracy: number
  /** null when no result in the run had provenance checked. */
  provenance: number | null
  overall: number
  passed: number
}

export const mean = (xs: number[]) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : 0)

/** Mean of the scores that exist; null if none do (e.g. provenance nobody checked). */
export function meanOf(xs: (number | null)[]): number | null {
  const present = xs.filter((x): x is number => x != null)
  return present.length ? mean(present) : null
}

/** Accuracy and provenance averaged, or accuracy alone when provenance wasn't checked. */
const combined = (accuracy: number, provenance: number | null) =>
  provenance == null ? accuracy : (accuracy + provenance) / 2

// Same rule as cli/honest_agent/thresholds.py, so the report agrees with `honest-agent notify`.
export const accuracyPasses = (r: ResultRow) => r.accuracy_min_score == null || r.accuracy_score >= r.accuracy_min_score
export const provenancePasses = (r: ResultRow) =>
  r.provenance_score == null || r.provenance_min_score == null || r.provenance_score >= r.provenance_min_score
export const passes = (r: ResultRow) => accuracyPasses(r) && provenancePasses(r)

export const overallOf = (r: ResultRow) => combined(r.accuracy_score, r.provenance_score)

export function runsOf(results: ResultRow[]): Run[] {
  const byRun = new Map<string, ResultRow[]>()
  for (const r of results) byRun.set(r.run_id, [...(byRun.get(r.run_id) ?? []), r])
  const runs = [...byRun.entries()].map(([run_id, rows]) => {
    const timestamp = rows.map((r) => r.run_timestamp).sort()[0].slice(0, 16)
    const accuracy = mean(rows.map((r) => r.accuracy_score))
    const provenance = meanOf(rows.map((r) => r.provenance_score))
    return {
      run_id,
      timestamp,
      date: timestamp.slice(0, 10),
      agent: agentOf(rows[0]),
      model: rows[0].model_name,
      results: rows,
      accuracy,
      provenance,
      overall: combined(accuracy, provenance),
      passed: rows.filter(passes).length,
    }
  })
  return runs.sort((a, b) => a.timestamp.localeCompare(b.timestamp))
}

export const UNKNOWN_AGENT = 'Unknown agent'
export const agentOf = (r: ResultRow) => r.agent_name ?? UNKNOWN_AGENT

/** Agents sorted by name, with results that predate agent tracking last. */
export function agentsOf(results: ResultRow[]): string[] {
  const named = [...new Set(results.map((r) => r.agent_name).filter((a): a is string => a != null))].sort()
  return results.some((r) => r.agent_name == null) ? [...named, UNKNOWN_AGENT] : named
}

export const modelsOf = (results: ResultRow[]) => [...new Set(results.map((r) => r.model_name))].sort()

/** Each eval's most recent title, so runs from before a title was added still show it. */
export function evalTitles(results: ResultRow[]): Map<string, string> {
  const titles = new Map<string, string>()
  const byTime = [...results].sort((a, b) => a.run_timestamp.localeCompare(b.run_timestamp))
  for (const r of byTime) if (r.eval_title) titles.set(r.eval_id, r.eval_title)
  return titles
}

export interface Eval {
  eval_id: string
  category: string
  title: string | null
}

/** Evals in first-seen order, with their category and title. */
export function evalsOf(results: ResultRow[], titles: Map<string, string>): Eval[] {
  const seen = new Map<string, string>()
  for (const r of results) if (!seen.has(r.eval_id)) seen.set(r.eval_id, r.category ?? 'Uncategorized')
  return [...seen.entries()].map(([eval_id, category]) => ({ eval_id, category, title: titles.get(eval_id) ?? null }))
}

/** Heatmap row for an eval: the title as label with the eval_id underneath, or the eval_id alone. */
export function evalHeatRow(q: Eval, accuracy: (number | null)[], provenance: (number | null)[]) {
  return {
    label: q.title ?? q.eval_id,
    sublabel: q.title ? q.eval_id : undefined,
    category: q.category,
    eval_id: q.eval_id,
    accuracy,
    provenance,
  }
}

/** Unique heatmap column label per run; the Heatmap shows the date and reveals the rest on hover. */
export function runColumns(runs: Run[]): string[] {
  const seen = new Map<string, number>()
  return runs.map((run) => {
    const base = run.timestamp
    const n = (seen.get(base) ?? 0) + 1
    seen.set(base, n)
    return n === 1 ? base : `${base} (${n})`
  })
}

export function toolCallsFor(data: ReportData, resultId: string): ToolCallRow[] {
  return data.tool_calls.filter((c) => c.result_id === resultId).sort((a, b) => a.call_index - b.call_index)
}

export function bucketCounts(scores: number[]) {
  const counts = { correct: 0, mostly: 0, partly: 0, wrong: 0 }
  for (const s of scores) {
    if (s >= 0.95) counts.correct++
    else if (s >= 0.75) counts.mostly++
    else if (s >= 0.4) counts.partly++
    else counts.wrong++
  }
  return counts
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/**
 * "2026-09-16 16:21" -> "16 Sep 2026, 16:21" ("16 Sep, 16:21" without the year).
 * Parsed by hand: run timestamps carry no timezone.
 */
export function formatRunTime(timestamp: string, { year = true } = {}): string {
  const [date, time] = timestamp.split(' ')
  const [y, m, d] = date.split('-').map(Number)
  return `${d} ${MONTHS[m - 1]}${year ? ` ${y}` : ''}${time ? `, ${time.slice(0, 5)}` : ''}`
}

/** "2026-09-16 ..." -> "16 Sep" */
export function formatRunDate(timestamp: string): string {
  const [, m, d] = timestamp.slice(0, 10).split('-').map(Number)
  return `${d} ${MONTHS[m - 1]}`
}

/**
 * Plain-text preview of a Markdown answer (Claude often bolds the number, e.g. "**228,626**").
 * Only removes emphasis markers that wrap words, so identifiers like q_revenue_1996 survive.
 */
export function stripMarkdown(s: string): string {
  return s
    .replace(/```\w*\n?/g, '')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/(\*\*|__)(.+?)\1/g, '$2')
    .replace(/(^|[\s(])[*_]([^*_\s][^*_]*?)[*_](?=[\s).,!?:;]|$)/g, '$1$2')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s*(?:[-*+]|\d+\.)\s+/gm, '')
    .replace(/\s+/g, ' ')
    .trim()
}

/** CSV text with every field quoted, so commas, quotes and newlines in answers survive. */
export function toCsv(header: string[], rows: (string | number | null)[][]): string {
  const cell = (v: string | number | null) => `"${String(v ?? '').replace(/"/g, '""')}"`
  return [header, ...rows].map((r) => r.map(cell).join(',')).join('\n')
}

/** "92.4%" -- one decimal, per the design system's number rules. */
export const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)
