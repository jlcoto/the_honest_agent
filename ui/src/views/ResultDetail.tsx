// Follows the design system's ui_kits/dashboard/Detail.jsx.
import { Fragment, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { PageHeader } from '../components/PageHeader'
import {
  accuracyPasses,
  agentOf,
  formatRunTime,
  pct,
  provenancePasses,
  evalTitles,
  stripMarkdown,
  toolCallsFor,
} from '../data/derive'
import type { ReportData, ResultRow, SourceRef, StepDetails, ToolCallRow } from '../data/types'
import { Badge, Button, Card, ScoreStat } from '../ds'

const mono: CSSProperties = { fontFamily: 'var(--font-mono)' }
const codeBlock: CSSProperties = {
  margin: 0,
  padding: '12px 14px',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--bg-sunken)',
  border: '1px solid var(--border-1)',
  font: '400 12.5px/1.55 var(--font-mono)',
  color: 'var(--fg-1)',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  overflowX: 'auto',
}
const para: CSSProperties = { margin: 0, font: 'var(--type-body)', color: 'var(--fg-1)', textWrap: 'pretty' }
const stack = (gap: number): CSSProperties => ({ display: 'flex', flexDirection: 'column', gap })

const COLLAPSED_LINES = 12

/** A code block that collapses past 12 lines, with a fade and a "Show all N lines" toggle. */
function Code({ text, color }: { text: string; color?: string }) {
  const [open, setOpen] = useState(false)
  const lines = text.split('\n')
  const long = lines.length > COLLAPSED_LINES
  return (
    <div style={{ ...stack(6), minWidth: 0 }}>
      <div style={{ position: 'relative' }}>
        <pre style={{ ...codeBlock, color: color ?? codeBlock.color }}>
          {long && !open ? lines.slice(0, COLLAPSED_LINES).join('\n') : text}
        </pre>
        {long && !open ? (
          <div
            style={{
              position: 'absolute',
              left: 1,
              right: 1,
              bottom: 1,
              height: 56,
              borderRadius: '0 0 var(--radius-sm) var(--radius-sm)',
              background: 'linear-gradient(to bottom, transparent, var(--bg-sunken))',
              pointerEvents: 'none',
            }}
          />
        ) : null}
      </div>
      {long ? (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          style={{
            alignSelf: 'flex-start',
            padding: 0,
            border: 0,
            background: 'none',
            cursor: 'pointer',
            font: '500 13px/1.4 var(--font-sans)',
            color: 'var(--accent)',
          }}
        >
          {open ? 'Show less' : `Show all ${lines.length} lines`}
        </button>
      ) : null}
    </div>
  )
}

/** Agent text as paragraphs, Markdown stripped -- the same treatment as the mockup. */
function Paragraphs({ text }: { text: string }) {
  return (
    <>
      {text.split(/\n{2,}/).map((p, i) => (
        <p key={i} style={para}>
          {stripMarkdown(p)}
        </p>
      ))}
    </>
  )
}

function Ids({ ids }: { ids: string[] | null }) {
  if (!ids?.length) return <span style={{ font: 'var(--type-small)', color: 'var(--fg-3)' }}>None</span>
  return (
    <span style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {ids.map((id) => (
        <Badge key={id} mono>
          {id}
        </Badge>
      ))}
    </span>
  )
}

// A plain decimal like "311928357.78" -- what extract_match normalizes numeric answers to.
const isPlainNumber = (s: string) => /^-?\d+(\.\d+)?$/.test(s.trim())
const decimalsOf = (s: string) => s.trim().split('.')[1]?.length ?? 0

/** Thousands separators for plain numbers, keeping every decimal as written; anything else unchanged. */
function formatValue(s: string): string {
  if (!isPlainNumber(s)) return s
  const [int, dec] = s.trim().split('.')
  return BigInt(int).toLocaleString('en-US') + (dec ? `.${dec}` : '')
}

/** |a - b| at the precision of the more precise side, or null if either isn't a plain number. */
function difference(a: string, b: string): string | null {
  if (!isPlainNumber(a) || !isPlainNumber(b)) return null
  const decimals = Math.max(decimalsOf(a), decimalsOf(b))
  return formatValue(Math.abs(Number(a) - Number(b)).toFixed(decimals))
}

function toleranceLabels(r: ResultRow): string[] {
  const labels: string[] = []
  if (r.accuracy_tolerance != null) labels.push(`± ${r.accuracy_tolerance}`)
  if (r.accuracy_tolerance_percent != null) labels.push(`± ${+(r.accuracy_tolerance_percent * 100).toFixed(4)}%`)
  return labels
}

const table: CSSProperties = {
  display: 'grid',
  border: '1px solid var(--border-1)',
  borderRadius: 'var(--radius-sm)',
  overflow: 'hidden',
}

const ledgerKey: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'center',
  gap: 2,
  padding: '12px 14px',
  background: 'var(--bg-sunken)',
  font: 'var(--type-label)',
  color: 'var(--fg-2)',
}
const ledgerValue: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'flex-end',
  padding: '12px 14px',
  minWidth: 0,
  font: '400 17px/1.35 var(--font-mono)',
  fontVariantNumeric: 'tabular-nums',
  textAlign: 'right',
  wordBreak: 'break-all',
}
const ledgerText: CSSProperties = { ...stack(10), padding: '12px 14px', minWidth: 0, justifyContent: 'center' }

interface LedgerRow {
  label: string
  hint?: string
  value: ReactNode
  /** Numbers are right-aligned in mono so digits line up; text reads left to right. */
  text?: boolean
  color?: string
}

/** Label/value rows in one bordered table: the label column on a sunken ground. */
function Ledger({ rows }: { rows: LedgerRow[] }) {
  return (
    <div style={{ ...table, gridTemplateColumns: 'minmax(120px, max-content) 1fr' }}>
      {rows.map((row, i) => {
        const divider = i ? '1px solid var(--border-1)' : 'none'
        return (
          <Fragment key={row.label}>
            <div style={{ ...ledgerKey, borderTop: divider }}>
              {row.label}
              {row.hint ? <span style={{ font: '400 12px/1.3 var(--font-sans)', color: 'var(--fg-3)' }}>{row.hint}</span> : null}
            </div>
            <div style={{ ...(row.text ? ledgerText : ledgerValue), borderTop: divider, color: row.color ?? 'var(--fg-1)' }}>
              {row.value}
            </div>
          </Fragment>
        )
      })}
    </div>
  )
}

const answerText = (text: string) => (text ? <Paragraphs text={text} /> : <p style={para}>(empty answer)</p>)

/** Expected vs. the agent's answer, laid out for the grading method that scored it. */
function AccuracyCard({ r }: { r: ResultRow }) {
  const ok = accuracyPasses(r)
  const tolerances = toleranceLabels(r)
  const extracted = r.accuracy_method === 'extract_match' ? r.extracted_answer : null
  const numeric = extracted != null && isPlainNumber(extracted) && isPlainNumber(r.expected_answer)
  const expected: LedgerRow = { label: 'Expected', hint: 'written in the eval', value: formatValue(r.expected_answer), text: !numeric }

  let rows: LedgerRow[]
  if (extracted != null) {
    rows = [expected, { label: 'Agent answer', hint: 'extracted by the grader', value: formatValue(extracted), text: !numeric }]
    const diff = numeric ? difference(extracted, r.expected_answer) : null
    if (diff != null) {
      rows.push({
        label: 'Difference',
        hint: tolerances.length ? `allowed ${tolerances.join(' or ')}` : 'must match exactly',
        value: diff,
        color: ok ? 'var(--acc-correct-ink)' : 'var(--acc-wrong-ink)',
      })
    }
  } else {
    rows = [{ ...expected, text: true }, { label: 'Agent answer', value: answerText(r.agent_answer), text: true }]
    if (r.accuracy_method === 'llm_judge') {
      rows.push({
        label: 'Judge',
        hint: r.grading_model ?? undefined,
        value: <p style={{ ...para, color: 'var(--fg-2)' }}>{r.accuracy_rationale ?? 'No rationale recorded.'}</p>,
        text: true,
      })
    }
  }

  return (
    <Card
      title="Accuracy"
      actions={
        <Badge tone={ok ? 'correct' : 'wrong'} dot>
          {ok ? 'Passed' : 'Failed'}
        </Badge>
      }
    >
      <Ledger rows={rows} />
      {extracted != null ? (
        <details>
          <summary style={{ cursor: 'pointer', listStyle: 'none', font: '500 13px/1.4 var(--font-sans)', color: 'var(--accent)' }}>
            Show the agent's full reply
          </summary>
          <div style={{ ...stack(10), marginTop: 10 }}>{answerText(r.agent_answer)}</div>
        </details>
      ) : null}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        <Badge mono>{r.accuracy_method}</Badge>
        {extracted != null
          ? tolerances.map((t) => (
              <Badge key={t} mono>
                tolerance {t}
              </Badge>
            ))
          : null}
        {r.accuracy_method === 'llm_judge' && r.grading_model ? <Badge mono>judge {r.grading_model}</Badge> : null}
      </div>
    </Card>
  )
}

// ---- Provenance ---------------------------------------------------------------------------

/** Splits a source name like SQL does: `table`, `schema.table` or `database.schema.table`; "quoted" parts keep their dots. */
function splitName(entry: string): string[] {
  const parts: string[] = []
  let current = ''
  let quoted = false
  for (const ch of entry.trim()) {
    if (ch === '"') quoted = !quoted
    else if (ch === '.' && !quoted) {
      parts.push(current)
      current = ''
    } else current += ch
  }
  return [...parts, current]
}

/** An `expected_sources` entry, with the eval's expected_database/expected_schema filling in what it leaves out
 * (the same rule as provenance.py's `_expected`). A null part means any. */
function expectedSource(entry: string, r: ResultRow): SourceRef {
  const parts = splitName(entry)
  const name = parts[parts.length - 1]
  const schema = parts.length >= 2 ? parts[parts.length - 2] : r.expected_schema
  const database = parts.length === 3 ? parts[0] : r.expected_database
  return { database, schema, name }
}

const same = (got: string | null, want: string | null) => want == null || (got ?? '').toLowerCase() === want.toLowerCase()
/** provenance.py's `_matches`: every part the expectation names must match. */
const matches = (got: SourceRef, want: SourceRef) =>
  same(got.database, want.database) && same(got.schema, want.schema) && same(got.name, want.name)
const fullName = (s: SourceRef) => [s.database, s.schema, s.name].map((p) => p ?? '?').join('.').toLowerCase()
const distinct = (xs: (string | null)[]) => [...new Map(xs.map((x) => [x?.toLowerCase() ?? null, x])).keys()]

const provValue: CSSProperties = {
  minWidth: 0,
  display: 'flex',
  flexWrap: 'wrap',
  alignItems: 'center',
  gap: '4px 14px',
  padding: '12px 14px',
  font: '400 15px/1.4 var(--font-mono)',
  wordBreak: 'break-all',
}
const unknown: CSSProperties = { font: 'italic 400 13px/1.4 var(--font-sans)', color: 'var(--fg-3)' }

/** Values at one level (database, schema or name), green if the expectation allows them, red if not. */
function Values({ values, ok }: { values: (string | null)[]; ok: (v: string | null) => boolean }) {
  if (values.length === 0) return <span style={unknown}>—</span>
  return (
    <>
      {values.map((v) =>
        v == null ? (
          <span key="?" style={unknown}>
            not specified
          </span>
        ) : (
          <span key={v} style={{ color: ok(v) ? 'var(--acc-correct-ink)' : 'var(--acc-wrong-ink)' }}>
            {v}
          </span>
        ),
      )}
    </>
  )
}

interface ProvRow {
  label: string
  expected: ReactNode
  queried: ReactNode
}

/** Expected | Agent queried, one row per level, styled like the Accuracy card's table. */
function ProvTable({ rows }: { rows: ProvRow[] }) {
  const head: CSSProperties = { ...ledgerKey, font: '500 12px/1.3 var(--font-sans)', color: 'var(--fg-3)', padding: '8px 14px' }
  return (
    <div style={{ ...table, gridTemplateColumns: 'minmax(120px, max-content) 1fr 1fr' }}>
      <div style={head} />
      <div style={head}>Expected</div>
      <div style={head}>Agent queried</div>
      {rows.map((row) => {
        const divider = '1px solid var(--border-1)'
        return (
          <Fragment key={row.label}>
            <div style={{ ...ledgerKey, borderTop: divider }}>{row.label}</div>
            <div style={{ ...provValue, borderTop: divider }}>{row.expected}</div>
            <div style={{ ...provValue, borderTop: divider }}>{row.queried}</div>
          </Fragment>
        )
      })}
    </div>
  )
}

const any = <span style={unknown}>any</span>

/** One expected source: its full name, an optional pill, and how it compares with what the agent read. */
function SourceSection({ want, queried, pill }: { want: SourceRef; queried: SourceRef[]; pill?: ReactNode }) {
  const read = (key: keyof SourceRef) => distinct(queried.map((s) => s[key]))
  const ok = (key: keyof SourceRef) => (v: string | null) => same(v, want[key])
  return (
    <div style={stack(8)}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ font: '500 13px/1.3 var(--font-mono)', color: 'var(--fg-1)', wordBreak: 'break-all' }}>
          {[want.database, want.schema, want.name].filter((p) => p != null).join('.')}
        </span>
        {pill}
      </div>
      <ProvTable
        rows={[
          { label: 'Database', expected: want.database ?? any, queried: <Values values={read('database')} ok={ok('database')} /> },
          { label: 'Schema', expected: want.schema ?? any, queried: <Values values={read('schema')} ok={ok('schema')} /> },
          {
            label: 'Source',
            expected: want.name,
            queried: queried.length ? (
              <Values values={read('name')} ok={ok('name')} />
            ) : (
              <span style={{ ...unknown, fontStyle: 'normal', color: 'var(--acc-wrong-ink)' }}>not read</span>
            ),
          },
        ]}
      />
    </div>
  )
}

function ToolsUsed({ r }: { r: ResultRow }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <span style={{ font: 'var(--type-label)', color: 'var(--fg-3)' }}>Tools used</span>
      <Ids ids={r.tools_used} />
    </div>
  )
}

const note: CSSProperties = { margin: 0, font: 'var(--type-small)', color: 'var(--fg-2)' }

/** Expected sources vs. what the agent's counted queries read (results.queried_sources). */
function ProvenanceCard({ r }: { r: ResultRow }) {
  if (r.provenance_score == null) {
    return (
      <Card title="Provenance" actions={<Badge dot>Not checked</Badge>}>
        <p style={note}>No provenance checks are defined for this eval.</p>
      </Card>
    )
  }
  const ok = provenancePasses(r)
  const queried = r.queried_sources ?? []
  const wanted = (r.expected_sources ?? []).map((e) => expectedSource(e, r))
  const pill = (
    <Badge tone={ok ? 'correct' : 'wrong'} dot>
      {ok ? 'Passed' : 'Failed'}
    </Badge>
  )

  if (wanted.length === 1) {
    // One source: the agent column lists everything read, and the card's pill is that source's result.
    return (
      <Card title="Provenance" actions={pill}>
        <SourceSection want={wanted[0]} queried={queried} />
        <ToolsUsed r={r} />
      </Card>
    )
  }

  // Several: each section shows what was read under that source's name; anything else goes under "Also read".
  const names = new Set(wanted.map((w) => w.name.toLowerCase()))
  const extra = queried.filter((s) => !names.has(s.name.toLowerCase()))
  const passed = wanted.map((w) => queried.some((s) => matches(s, w)))
  return (
    <Card title="Provenance" actions={pill}>
      <div style={stack(16)}>
        {wanted.map((w, i) => (
          <SourceSection
            key={fullName(w)}
            want={w}
            queried={queried.filter((s) => s.name.toLowerCase() === w.name.toLowerCase())}
            pill={
              <Badge size="sm" tone={passed[i] ? 'correct' : 'wrong'} dot>
                {passed[i] ? 'Passed' : 'Failed'}
              </Badge>
            }
          />
        ))}
      </div>
      {extra.length ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ font: 'var(--type-label)', color: 'var(--fg-3)' }}>Also read</span>
          <Ids ids={extra.map(fullName)} />
        </div>
      ) : null}
      <ToolsUsed r={r} />
      <p style={note}>
        Score <b style={{ fontWeight: 500, color: 'var(--fg-1)' }}>{pct(r.provenance_score)}</b>: {passed.filter(Boolean).length} of{' '}
        {wanted.length} sources passed, minimum {pct(r.provenance_min_score)}
      </p>
    </Card>
  )
}

/** Steps the agent took against the run's limit: one bar segment per allowed step. The last
 * segment turns red, with a note, only when the agent used them all without answering. */
function StepsStat({ r }: { r: ResultRow }) {
  if (r.steps == null) return <ScoreStat label="Steps" format="raw" value="—" caption="Not recorded for this run" />
  const { steps, max_steps: max } = r
  return (
    <div style={stack(8)}>
      <ScoreStat label="Steps" format="raw" value={steps} />
      {max != null ? (
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${max}, 1fr)`, gap: 4 }}>
          {Array.from({ length: max }, (_, i) => (
            <div
              key={i}
              style={{
                height: 8,
                borderRadius: 2,
                background:
                  r.hit_step_limit && i === steps - 1
                    ? 'var(--acc-wrong)'
                    : i < steps
                      ? 'color-mix(in srgb, var(--ink-data) 75%, transparent)'
                      : 'var(--chart-empty)',
              }}
            />
          ))}
        </div>
      ) : null}
      {r.hit_step_limit ? (
        <span style={{ font: 'var(--type-small)', color: 'var(--acc-wrong-ink)' }}>Hit the limit before answering</span>
      ) : null}
    </div>
  )
}

const PREVIEW_CHARS = 60

// A query as one line: comments dropped, whitespace collapsed, cut to PREVIEW_CHARS.
function queryPreview(sql: string): string {
  const line = sql
    .replace(/--[^\n]*/g, '')
    .replace(/\s+/g, ' ')
    .replace(/\(\s/g, '(')
    .replace(/\s\)/g, ')')
    .replace(/\s*;\s*$/, '')
    .trim()
  return line.length > PREVIEW_CHARS ? `${line.slice(0, PREVIEW_CHARS - 1).trimEnd()}…` : line
}

const errorText: CSSProperties = { font: 'var(--type-small)', color: 'var(--acc-wrong-ink)' }
const stepLink: CSSProperties = {
  all: 'unset',
  cursor: 'pointer',
  font: 'var(--type-small)',
  color: 'var(--fg-3)',
  textDecoration: 'underline',
  textDecorationColor: 'var(--border-2)',
  textUnderlineOffset: 2,
  whiteSpace: 'nowrap',
}
const sqlCell: CSSProperties = { padding: '11px 14px 11px 0', borderBottom: '1px solid var(--border-1)', verticalAlign: 'baseline' }

function StatusDot({ error }: { error: boolean }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: 7,
        height: 7,
        borderRadius: '50%',
        marginRight: 8,
        verticalAlign: 'middle',
        background: error ? 'var(--acc-wrong)' : 'var(--green-500)',
      }}
    />
  )
}

/** The queries the agent sent to the warehouse, one line each: a link to the step that ran
 * it in the Trace, a dot for whether it ran or failed, and the query. A row opens to the full
 * SQL, plus the error when it failed or the value when it returned exactly one row and one
 * column. SQL a tool only generated (e.g. Cortex Analyst) wasn't sent, so it isn't listed. */
function SqlCallsCard({ calls }: { calls: ToolCallRow[] }) {
  const [open, setOpen] = useState<Set<number>>(new Set())
  const sent = calls.filter((c) => !c.generated)
  const toggle = (i: number) =>
    setOpen((was) => {
      const now = new Set(was)
      if (now.has(i)) now.delete(i)
      else now.add(i)
      return now
    })
  const goToStep = openStep
  useEffect(() => {
    const onOpen = (e: Event) => {
      const i = (e as CustomEvent<number>).detail
      setOpen((was) => new Set(was).add(i))
      requestAnimationFrame(() => flash(document.getElementById(`sql-call-${i}`)))
    }
    window.addEventListener(OPEN_SQL_CALL, onOpen)
    return () => window.removeEventListener(OPEN_SQL_CALL, onOpen)
  }, [])
  const legend = (
    <div style={{ display: 'flex', gap: 16, font: 'var(--type-small)', color: 'var(--fg-3)' }}>
      <span>
        <StatusDot error={false} />
        ran
      </span>
      <span>
        <StatusDot error />
        error
      </span>
    </div>
  )

  return (
    <Card title={`SQL calls (${sent.length})`} actions={sent.length ? legend : undefined}>
      {sent.length === 0 ? (
        <p style={note}>No SQL was run for this answer.</p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <tbody>
              {sent.map((c, i) => {
                const sql = (parseJson(c.payload) as { sql?: string } | null)?.sql ?? c.payload
                const isOpen = open.has(c.call_index)
                const line = i === sent.length - 1 && !isOpen ? 'none' : '1px solid var(--border-1)'
                return (
                  <Fragment key={c.call_index}>
                    <tr id={`sql-call-${c.call_index}`} onClick={() => toggle(c.call_index)} style={{ cursor: 'pointer' }}>
                      <td style={{ ...sqlCell, borderBottom: line, width: 64 }}>
                        {c.step != null ? (
                          <button
                            type="button"
                            style={stepLink}
                            onClick={(e) => {
                              e.stopPropagation()
                              goToStep(c.step!)
                            }}
                          >
                            Step {c.step}
                          </button>
                        ) : null}
                      </td>
                      <td style={{ ...sqlCell, borderBottom: line }}>
                        <StatusDot error={!!c.is_error} />
                        <span style={{ font: '400 12.5px/1.4 var(--font-mono)', color: 'var(--fg-1)', verticalAlign: 'middle' }}>
                          {queryPreview(sql)}
                        </span>
                      </td>
                    </tr>
                    {isOpen ? (
                      <tr>
                        <td style={{ borderBottom: i === sent.length - 1 ? 'none' : '1px solid var(--border-1)' }} />
                        <td style={{ padding: '14px 14px 14px 0', borderBottom: i === sent.length - 1 ? 'none' : '1px solid var(--border-1)' }}>
                          <div style={stack(10)}>
                            <Code text={sql} />
                            {c.is_error && c.error ? <span style={errorText}>{c.error}</span> : null}
                            {!c.is_error && c.result_value != null ? (
                              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', padding: '8px 12px', borderRadius: 'var(--radius-sm)', background: 'var(--bg-sunken)', border: '1px solid var(--border-1)' }}>
                                <span style={{ font: 'var(--type-label)', color: 'var(--fg-3)' }}>{c.result_column}</span>
                                <span style={{ font: '500 15px/1.2 var(--font-mono)', color: 'var(--fg-1)' }}>{c.result_value}</span>
                              </div>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

const parseJson = (s: string): unknown => {
  try {
    return JSON.parse(s)
  } catch {
    return null
  }
}

interface Block {
  type?: string
  text?: string
  thinking?: string
  id?: string
  name?: string
  input?: Record<string, unknown>
  tool_use_id?: string
  content?: unknown
  is_error?: boolean
}
interface Message {
  role?: string
  content?: unknown
}

// The two cards point at each other: SQL calls opens a step in the Trace, and the Trace
// opens a query in SQL calls. Each card owns what's open, so they talk through events.
const OPEN_STEP = 'honest-agent:open-step'
const OPEN_SQL_CALL = 'honest-agent:open-sql-call'
const openStep = (step: number) => window.dispatchEvent(new CustomEvent(OPEN_STEP, { detail: step }))
const openSqlCall = (callIndex: number) => window.dispatchEvent(new CustomEvent(OPEN_SQL_CALL, { detail: callIndex }))
const flash = (el: HTMLElement | null) => {
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el?.animate([{ background: 'color-mix(in srgb, var(--green-300) 40%, transparent)' }, { background: 'transparent' }], {
    duration: 1600,
    easing: 'ease-out',
  })
}

const blocksOf = (m: Message): Block[] => (Array.isArray(m.content) ? (m.content as Block[]) : [])
const resultText = (content: unknown): string =>
  Array.isArray(content) ? content.map((c: Block) => c.text ?? JSON.stringify(c)).join('\n') : String(content ?? '')
const normSql = (s: string) => s.replace(/--[^\n]*/g, '').replace(/\s+/g, ' ').replace(/\s*;\s*$/, '').trim().toLowerCase()
const cut = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s)
const argText = (v: unknown) => (typeof v === 'string' ? v : JSON.stringify(v))
const secs = (ms: number | null | undefined) => (ms == null ? null : `${(ms / 1000).toFixed(1)}s`)

interface Call {
  use: Block
  result: Block | undefined
  sqlRow: ToolCallRow | undefined // the SQL calls row this call ran, if it sent SQL
  generated: ToolCallRow | undefined // SQL the tool returned without running it (Cortex Analyst)
}
interface Step {
  n: number
  blocks: Block[]
  calls: Call[]
}

/** The agent's turns as steps: each model reply with the tool calls it made and what came back. */
function stepsOf(messages: Message[], sqlCalls: ToolCallRow[]): Step[] {
  const results = new Map<string, Block>()
  for (const m of messages) for (const b of blocksOf(m)) if (b.type === 'tool_result' && b.tool_use_id) results.set(b.tool_use_id, b)
  const steps: Step[] = []
  for (const m of messages) {
    if (m.role !== 'assistant') continue
    const n = steps.length + 1
    const rows = sqlCalls.filter((c) => c.step === n)
    const used = new Set<ToolCallRow>()
    const take = (match: (c: ToolCallRow) => boolean) => {
      const row = rows.find((c) => !used.has(c) && match(c))
      if (row) used.add(row)
      return row
    }
    const calls = blocksOf(m)
      .filter((b) => b.type === 'tool_use')
      .map((use) => {
        const values = Object.values(use.input ?? {})
        const sqlOf = (c: ToolCallRow) => (parseJson(c.payload) as { sql?: string } | null)?.sql
        return {
          use,
          result: use.id ? results.get(use.id) : undefined,
          sqlRow: take((c) => !c.generated && c.tool_name === use.name && values.includes(sqlOf(c))),
          generated: take((c) => !!c.generated && c.tool_name === use.name),
        }
      })
    steps.push({ n, blocks: blocksOf(m), calls })
  }
  return steps
}

// The step a generated statement was later run in, if any.
function ranLater(generated: ToolCallRow, sqlCalls: ToolCallRow[]): number | null {
  const sql = normSql((parseJson(generated.payload) as { sql?: string } | null)?.sql ?? '')
  const hit = sqlCalls.find(
    (c) => !c.generated && !c.is_error && (c.step ?? 0) > (generated.step ?? 0) && normSql((parseJson(c.payload) as { sql?: string } | null)?.sql ?? '') === sql,
  )
  return hit?.step ?? null
}

const traceMono = (size: number, color = 'var(--fg-2)'): CSSProperties => ({ font: `400 ${size}px/1.5 var(--font-mono)`, color, wordBreak: 'break-word' })
const muted: CSSProperties = { font: 'var(--type-small)', color: 'var(--fg-3)' }
const linkish: CSSProperties = { all: 'unset', cursor: 'pointer', textDecoration: 'underline', textDecorationColor: 'var(--border-2)', textUnderlineOffset: 2 }
const RAW_HEIGHT = 220

/** A tool's output exactly as it came back, cut to a first chunk with "Show all output". */
function RawOutput({ text, error }: { text: string; error: boolean }) {
  const [all, setAll] = useState(false)
  const [long, setLong] = useState(false)
  const ref = useRef<HTMLPreElement>(null)
  useLayoutEffect(() => {
    if (ref.current) setLong(ref.current.scrollHeight > RAW_HEIGHT + 2)
  }, [text])
  return (
    <div style={{ ...stack(6), position: 'relative' }}>
      <pre ref={ref} style={{ ...codeBlock, color: error ? 'var(--acc-wrong-ink)' : codeBlock.color, maxHeight: all ? 'none' : RAW_HEIGHT, overflow: 'hidden' }}>
        {text || '(empty)'}
      </pre>
      {long && !all ? (
        <div
          style={{
            position: 'absolute', left: 1, right: 1, bottom: 26, height: 48, pointerEvents: 'none',
            borderRadius: '0 0 var(--radius-sm) var(--radius-sm)', background: 'linear-gradient(to bottom, transparent, var(--bg-sunken))',
          }}
        />
      ) : null}
      {long ? (
        <button type="button" onClick={() => setAll(!all)} style={{ all: 'unset', cursor: 'pointer', font: 'var(--type-label)', color: 'var(--accent)' }}>
          {all ? 'Show less' : 'Show all output'}
        </button>
      ) : null}
    </div>
  )
}

/** One tool call: its line (tool and arguments, with the call's time once open), then, open,
 * the arguments in full when the line had to cut them, and the raw output. */
function TraceCall({ call, open, ms, sqlCalls }: { call: Call; open: boolean; ms: number | null | undefined; sqlCalls: ToolCallRow[] }) {
  const { use, result, sqlRow, generated } = call
  const input = use.input ?? {}
  const sql = sqlRow ? ((parseJson(sqlRow.payload) as { sql?: string } | null)?.sql ?? '') : null
  const args = Object.entries(input).map(([k, v]) => `${k}: ${argText(v)}`).join(', ')
  const message = typeof input.message === 'string' ? input.message : null
  const shown = sql != null ? queryPreview(sql) : message != null ? `("${cut(message, 60)}")` : `(${cut(args, 70)})`
  const wasCut = sql != null || (message != null ? message.length > 60 : args.length > 70)
  const failed = !!result?.is_error
  const later = generated ? ranLater(generated, sqlCalls) : null
  const notes: ReactNode[] = []
  if (failed) notes.push(<span key="f" style={{ color: 'var(--acc-wrong-ink)' }}>failed</span>)
  if (generated)
    notes.push(
      later ? (
        <span key="g">returned SQL · ran later in step {later}</span>
      ) : (
        <span key="g" style={{ color: 'var(--acc-wrong-ink)' }}>returned SQL · never run in this trace</span>
      ),
    )
  if (sqlRow)
    notes.push(
      <button key="s" type="button" style={linkish} onClick={() => openSqlCall(sqlRow.call_index)}>
        SQL calls
      </button>,
    )
  return (
    <div style={stack(6)}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2px 10px', alignItems: 'baseline' }}>
        <span style={traceMono(12.5)}>
          <span style={{ color: 'var(--fg-1)', fontWeight: 500 }}>{use.name}</span>
          <span style={{ color: 'var(--fg-3)' }}>
            {sql != null ? ' ' : ''}
            {shown}
          </span>
          {open && ms != null ? <span style={{ color: 'var(--fg-3)' }}> · {secs(ms)}</span> : null}
        </span>
        {notes.length ? (
          <span style={muted}>
            {notes.map((n, i) => (
              <Fragment key={i}>
                {i ? ' · ' : ''}
                {n}
              </Fragment>
            ))}
          </span>
        ) : null}
      </div>
      {open && wasCut ? (
        sql != null ? (
          <Code text={sql} />
        ) : (
          <span style={{ ...traceMono(12, 'var(--fg-3)'), whiteSpace: 'pre-wrap' }}>
            {Object.entries(input).map(([k, v]) => `${k}: ${argText(v)}`).join('\n')}
          </span>
        )
      ) : null}
      {open ? <RawOutput text={resultText(result?.content)} error={failed} /> : null}
    </div>
  )
}

const said = (blocks: Block[]) =>
  blocks
    .filter((b) => b.type === 'text')
    .map((b) => b.text ?? '')
    .join('\n\n')
    .trim()
const thought = (blocks: Block[]) => blocks.find((b) => b.type === 'thinking')

/** How the agent worked through the question: the question, one line per step (what the
 * agent said and the tools it called), each opening to the full text, every call with its
 * arguments and raw output, and the step's tokens and time; then the final answer, or the
 * step limit. */
function TraceCard({ r, raw, details, sqlCalls }: { r: ResultRow; raw: string | undefined; details: StepDetails | null; sqlCalls: ToolCallRow[] }) {
  const [open, setOpen] = useState<Set<number>>(new Set())
  useEffect(() => {
    const onOpen = (e: Event) => {
      const n = (e as CustomEvent<number>).detail
      setOpen((was) => new Set(was).add(n))
      requestAnimationFrame(() => flash(document.getElementById(`step-${n}`)))
    }
    window.addEventListener(OPEN_STEP, onOpen)
    return () => window.removeEventListener(OPEN_STEP, onOpen)
  }, [])

  const messages = raw ? parseJson(raw) : null
  if (!Array.isArray(messages))
    return (
      <Card title="Trace">
        <pre style={codeBlock}>{raw ?? 'No trace recorded.'}</pre>
      </Card>
    )
  const steps = stepsOf(messages as Message[], sqlCalls)
  const last = steps[steps.length - 1]
  const answered = last && last.calls.length === 0
  const shownSteps = answered ? steps.slice(0, -1) : steps
  const toggle = (n: number) =>
    setOpen((was) => {
      const now = new Set(was)
      if (now.has(n)) now.delete(n)
      else now.add(n)
      return now
    })
  const allOpen = shownSteps.length > 0 && shownSteps.every((s) => open.has(s.n))
  const tokens = (r.agent_input_tokens ?? 0) + (r.agent_output_tokens ?? 0)
  const question = (messages as Message[])[0]?.content
  const line = '1px solid var(--border-1)'

  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <h3 style={{ margin: 0, font: 'var(--type-h2)', color: 'var(--fg-1)', letterSpacing: '-0.01em' }}>Trace</h3>
          <span style={muted}>
            {steps.length} steps · {tokens.toLocaleString('en-US')} tokens
          </span>
        </div>
        {shownSteps.length ? (
          <button
            type="button"
            style={{ all: 'unset', cursor: 'pointer', font: 'var(--type-label)', color: 'var(--accent)' }}
            onClick={() => setOpen(allOpen ? new Set() : new Set(shownSteps.map((s) => s.n)))}
          >
            {allOpen ? 'Collapse all' : 'Expand all'}
          </button>
        ) : null}
      </div>
      <div>
        <div style={{ ...stack(4), paddingBottom: 14, borderBottom: line }}>
          <span style={{ font: 'var(--type-label)', color: 'var(--fg-3)' }}>Prompt</span>
          <p style={{ ...para, fontSize: 15 }}>{typeof question === 'string' ? question.trim() : r.prompt}</p>
        </div>
        {shownSteps.map((s) => {
          const isOpen = open.has(s.n)
          const text = said(s.blocks)
          const think = thought(s.blocks)
          const stats = details?.steps[s.n - 1]
          const tools = new Map<string, { n: number; failed: boolean }>()
          for (const c of s.calls) {
            const t = tools.get(c.use.name ?? '?') ?? { n: 0, failed: false }
            tools.set(c.use.name ?? '?', { n: t.n + 1, failed: t.failed || !!c.result?.is_error })
          }
          return (
            <div key={s.n} id={`step-${s.n}`} style={{ borderBottom: line, scrollMarginTop: 16 }}>
              <div
                onClick={() => toggle(s.n)}
                style={{ display: 'grid', gridTemplateColumns: '18px 52px minmax(0, 1fr) auto', gap: '0 8px', alignItems: 'baseline', padding: '11px 0', cursor: 'pointer' }}
              >
                <span style={{ fontSize: 11, color: 'var(--fg-2)', textAlign: 'center', display: 'inline-block', transform: isOpen ? 'rotate(90deg)' : 'none', transition: 'transform .15s' }}>
                  ▶
                </span>
                <span style={{ font: '500 12px/1 var(--font-mono)', color: 'var(--fg-3)' }}>Step {s.n}</span>
                {isOpen ? (
                  <span />
                ) : (
                  <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--fg-1)' }}>
                    {text ? stripMarkdown(text) : <i style={{ color: 'var(--fg-3)' }}>{think ? 'Thought (hidden)' : 'No text'}</i>}
                  </span>
                )}
                {isOpen ? (
                  <span />
                ) : (
                  <span style={{ ...traceMono(12, 'var(--fg-3)'), whiteSpace: 'nowrap', textAlign: 'right' }}>
                    {[...tools].map(([name, t], i) => (
                      <Fragment key={name}>
                        {i ? ', ' : ''}
                        <span style={t.failed ? { color: 'var(--acc-wrong-ink)' } : undefined}>
                          {name}
                          {t.n > 1 ? ` ×${t.n}` : ''}
                          {t.failed ? ' ✕' : ''}
                        </span>
                      </Fragment>
                    ))}
                  </span>
                )}
              </div>
              {isOpen ? (
                <div style={{ ...stack(6), padding: '0 0 14px 86px', marginTop: -30 }}>
                  {think ? (
                    <i style={muted}>{think.thinking ? think.thinking : 'Thought before acting (hidden by the provider)'}</i>
                  ) : null}
                  {text ? <Paragraphs text={text} /> : null}
                  {stats ? (
                    <span style={traceMono(12, 'var(--fg-3)')}>
                      {stats.input_tokens.toLocaleString('en-US')} in · {stats.output_tokens.toLocaleString('en-US')} out
                      {stats.duration_ms != null ? ` · ${secs(stats.duration_ms)}` : ''}
                      {stats.stop_reason === 'tool_use' ? ' · stopped for tool calls' : stats.stop_reason === 'end_turn' ? ' · stopped for the answer' : stats.stop_reason ? ` · stopped: ${stats.stop_reason}` : ''}
                    </span>
                  ) : null}
                  <div style={{ ...stack(14), marginTop: 4 }}>
                    {s.calls.map((c, i) => (
                      <TraceCall key={c.use.id ?? i} call={c} open ms={c.use.id ? details?.tool_ms[c.use.id] : null} sqlCalls={sqlCalls} />
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          )
        })}
        <div style={{ ...stack(6), paddingTop: 14 }}>
          {answered ? (
            <>
              <span style={{ font: 'var(--type-label)', color: 'var(--fg-3)' }}>Final answer · step {last.n}</span>
              {said(last.blocks) ? <Paragraphs text={said(last.blocks)} /> : <p style={para}>(empty answer)</p>}
            </>
          ) : (
            <>
              <span style={{ font: 'var(--type-label)', color: 'var(--fg-3)' }}>No answer</span>
              <p style={{ ...para, color: 'var(--acc-wrong-ink)' }}>
                {r.hit_step_limit
                  ? `Hit the limit before answering: step ${steps.length}${r.max_steps ? ` of ${r.max_steps}` : ''} still called a tool.`
                  : 'The agent stopped without an answer.'}
              </p>
            </>
          )}
        </div>
      </div>
    </Card>
  )
}

export function ResultDetail({ data, resultId }: { data: ReportData; resultId: string }) {
  const r = data.results.find((x) => x.result_id === resultId)
  const back = (
    <Button variant="secondary" size="sm" icon="arrow-left" onClick={() => window.history.back()}>
      Back
    </Button>
  )
  if (!r) return <PageHeader title="Result not found" subtitle={`No result with id ${resultId} in this report.`}>{back}</PageHeader>

  const accOk = accuracyPasses(r)
  const provOk = provenancePasses(r)
  const calls = toolCallsFor(data, r.result_id)
  const log = data.agent_logs.find((l) => l.result_id === r.result_id)
  const details = log?.step_details ? (parseJson(log.step_details) as StepDetails | null) : null
  const tokens = (r.agent_input_tokens ?? 0) + (r.agent_output_tokens ?? 0)
  const title = evalTitles(data.results).get(r.eval_id)
  const fmt = (n: number | null) => (n ?? 0).toLocaleString('en-US')

  return (
    <div style={stack(20)}>
      <PageHeader
        title={title ?? <span style={{ ...mono, fontWeight: 500 }}>{r.eval_id}</span>}
        subtitle={
          <>
            <span style={mono}>{r.eval_id}</span> · {r.category ?? 'Uncategorized'} · {formatRunTime(r.run_timestamp)} ·{' '}
            {agentOf(r)} · <span style={mono}>{r.model_name}</span>
          </>
        }
      >
        <Badge tone={accOk ? 'correct' : 'wrong'} dot>
          Accuracy
        </Badge>
        {r.provenance_score == null ? (
          <Badge dot>Provenance not checked</Badge>
        ) : (
          <Badge tone={provOk ? 'correct' : 'wrong'} dot>
            Provenance
          </Badge>
        )}
        {back}
      </PageHeader>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'auto 1fr',
          gap: '4px 14px',
          alignItems: 'baseline',
          padding: '6px 0 6px 16px',
          borderLeft: '5px solid var(--green-300)',
          // Optical alignment: the cards below have rounded corners, so their edge reads a little further in.
          marginLeft: 4,
        }}
      >
        <span style={{ font: 'var(--type-label)', color: 'var(--fg-3)', letterSpacing: 'var(--ls-caps)', textTransform: 'uppercase' }}>Prompt</span>
        <p style={{ margin: 0, font: '400 18px/1.45 var(--font-sans)', color: 'var(--fg-1)', textWrap: 'pretty' }}>
          {r.prompt}
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
        <Card>
          <ScoreStat label="Accuracy" value={r.accuracy_score} caption={`min score ${pct(r.accuracy_min_score)}`} />
        </Card>
        <Card>
          {r.provenance_score == null ? (
            <ScoreStat label="Provenance" format="raw" value="Not checked" caption="This eval expects no sources" />
          ) : (
            <ScoreStat label="Provenance" value={r.provenance_score} caption={`min score ${pct(r.provenance_min_score)}`} />
          )}
        </Card>
        <Card>
          {r.agent_input_tokens == null && r.agent_output_tokens == null ? (
            <ScoreStat label="Agent tokens" format="raw" value="—" caption="Not recorded for this run" />
          ) : (
            <ScoreStat
              label="Agent tokens"
              format="raw"
              value={tokens.toLocaleString('en-US')}
              caption={`${fmt(r.agent_input_tokens)} in · ${fmt(r.agent_output_tokens)} out`}
            />
          )}
        </Card>
        <Card>
          <StepsStat r={r} />
        </Card>
      </div>

      <AccuracyCard r={r} />

      <ProvenanceCard r={r} />

      <SqlCallsCard calls={calls} />

      <TraceCard r={r} raw={log?.agent_trace} details={details} sqlCalls={calls} />
    </div>
  )
}
