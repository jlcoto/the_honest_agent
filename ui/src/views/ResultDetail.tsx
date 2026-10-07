// Follows the design system's ui_kits/dashboard/Detail.jsx.
import { Fragment, useState, type CSSProperties, type ReactNode } from 'react'
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
import type { ReportData, ResultRow, SourceRef, ToolCallRow } from '../data/types'
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

function Num({ n, label }: { n: number; label: ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ font: '500 12px/1 var(--font-mono)', color: 'var(--fg-3)', minWidth: 18 }}>{n}</span>
      <span style={{ font: '500 13px/1 var(--font-sans)', color: 'var(--fg-2)' }}>{label}</span>
    </div>
  )
}

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

const firstSentence = (s: string) => s.split(/(?<=\.)\s/)[0]
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

/** The queries the agent sent to the warehouse, one row each: the step that ran it (a link
 * to that step in the Trace) and the query on one line, with the error when it failed.
 * A row opens to the full SQL and, when the query returned exactly one value, that value.
 * SQL a tool only generated (e.g. Cortex Analyst) wasn't sent, so it isn't listed. */
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
  const goToStep = (step: number) =>
    document.getElementById(`step-${step}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <Card title={`SQL calls (${sent.length})`}>
      {sent.length === 0 ? (
        <p style={note}>No SQL was run for this answer.</p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['Step', 'Query'].map((h) => (
                  <th
                    key={h}
                    style={{ font: 'var(--type-label)', color: 'var(--fg-3)', textAlign: 'left', padding: '0 14px 10px 0', borderBottom: '1px solid var(--border-1)' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sent.map((c) => {
                const sql = (parseJson(c.payload) as { sql?: string } | null)?.sql ?? c.payload
                const isOpen = open.has(c.call_index)
                return (
                  <Fragment key={c.call_index}>
                    <tr onClick={() => toggle(c.call_index)} style={{ cursor: 'pointer' }}>
                      <td style={{ ...sqlCell, width: 64 }}>
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
                      <td style={sqlCell}>
                        <span style={{ font: '400 12.5px/1.4 var(--font-mono)', color: 'var(--fg-1)' }}>{queryPreview(sql)}</span>
                        {c.is_error && c.error && !isOpen ? <div style={{ ...errorText, marginTop: 3 }}>{firstSentence(c.error)}</div> : null}
                      </td>
                    </tr>
                    {isOpen ? (
                      <tr>
                        <td style={{ borderBottom: '1px solid var(--border-1)' }} />
                        <td style={{ padding: '14px 14px 14px 0', borderBottom: '1px solid var(--border-1)' }}>
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
  name?: string
  input?: unknown
  content?: unknown
  is_error?: boolean
}
interface Message {
  role?: string
  content?: unknown
}

function TraceBlock({ block }: { block: Block }) {
  if (block.type === 'text') return <Paragraphs text={block.text ?? ''} />
  if (block.type === 'tool_use') {
    const input = block.input as { sql?: unknown } | undefined
    return (
      <>
        <span style={{ font: '400 12px/1.3 var(--font-mono)', color: 'var(--fg-3)' }}>{block.name}</span>
        <Code text={typeof input?.sql === 'string' ? input.sql : JSON.stringify(block.input, null, 2)} />
      </>
    )
  }
  if (block.type === 'tool_result') {
    const content = Array.isArray(block.content)
      ? block.content.map((c: Block) => c.text ?? JSON.stringify(c)).join('\n')
      : String(block.content ?? '')
    return <Code text={content} color={block.is_error ? 'var(--acc-wrong-ink)' : undefined} />
  }
  return <Code text={JSON.stringify(block, null, 2)} />
}

// A user message carrying only tool results is the tool talking back, so it's labelled that way.
function roleLabel(m: Message): string {
  const blocks = Array.isArray(m.content) ? (m.content as Block[]) : []
  if (m.role === 'user' && blocks.length > 0 && blocks.every((b) => b.type === 'tool_result')) return 'Tool result'
  return m.role === 'assistant' ? 'Assistant' : 'User'
}

function Trace({ raw }: { raw: string | undefined }) {
  const messages = raw ? parseJson(raw) : null
  if (!Array.isArray(messages)) return <pre style={codeBlock}>{raw ?? 'No trace recorded.'}</pre>
  let step = 0
  const steps = (messages as Message[]).map((m) => (m.role === 'assistant' ? ++step : step))
  return (
    <div style={stack(16)}>
      {(messages as Message[]).map((m, i) => (
        <div
          key={i}
          // Each assistant message is one step; SQL calls link here.
          id={m.role === 'assistant' ? `step-${steps[i]}` : undefined}
          style={{ ...stack(8), paddingTop: i ? 16 : 0, borderTop: i ? '1px solid var(--border-1)' : 'none', scrollMarginTop: 16 }}
        >
          <Num n={i + 1} label={roleLabel(m)} />
          {typeof m.content === 'string' ? (
            <Paragraphs text={m.content} />
          ) : (
            (Array.isArray(m.content) ? (m.content as Block[]) : []).map((b, j) => <TraceBlock key={j} block={b} />)
          )}
        </div>
      ))}
    </div>
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
  const trace = data.agent_logs.find((l) => l.result_id === r.result_id)?.agent_trace
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
        <span style={{ font: 'var(--type-label)', color: 'var(--fg-3)', letterSpacing: 'var(--ls-caps)' }}>Q</span>
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

      <Card title="Trace">
        <Trace raw={trace} />
      </Card>
    </div>
  )
}
