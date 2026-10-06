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
import type { ReportData, ResultRow } from '../data/types'
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

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ ...stack(8), minWidth: 0 }}>
      <span style={{ font: 'var(--type-label)', color: 'var(--fg-2)' }}>{label}</span>
      {children}
    </div>
  )
}

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
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(120px, max-content) 1fr',
        border: '1px solid var(--border-1)',
        borderRadius: 'var(--radius-sm)',
        overflow: 'hidden',
      }}
    >
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
  return (
    <div style={stack(16)}>
      {(messages as Message[]).map((m, i) => (
        <div key={i} style={{ ...stack(8), paddingTop: i ? 16 : 0, borderTop: i ? '1px solid var(--border-1)' : 'none' }}>
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
          borderLeft: '3px solid var(--accent)',
        }}
      >
        <span style={{ font: 'var(--type-label)', color: 'var(--fg-3)', letterSpacing: 'var(--ls-caps)' }}>Q</span>
        <p style={{ margin: 0, font: '400 18px/1.45 var(--font-sans)', color: 'var(--fg-1)', textWrap: 'pretty', maxWidth: '68ch' }}>
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
          <ScoreStat
            label="Latency"
            format="raw"
            value={r.latency_ms == null ? '—' : `${(r.latency_ms / 1000).toFixed(1)}s`}
            caption="Agent time, excluding grading"
          />
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
      </div>

      <AccuracyCard r={r} />

      <Card title="Provenance">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 20 }}>
          <Field label="Expected sources">
            <Ids ids={r.expected_sources} />
          </Field>
          <Field label="Expected database / schema">
            <span style={{ font: '400 13px/1.4 var(--font-mono)' }}>
              {r.expected_database ?? '—'} / {r.expected_schema ?? '—'}
            </span>
          </Field>
          <Field label="Tools used">
            <Ids ids={r.tools_used} />
          </Field>
        </div>
      </Card>

      <Card title={`SQL calls (${calls.length})`}>
        {calls.length === 0 ? (
          <p style={{ margin: 0, font: 'var(--type-small)', color: 'var(--fg-3)' }}>No SQL was captured for this answer.</p>
        ) : (
          <div style={stack(16)}>
            {calls.map((c) => {
              const payload = parseJson(c.payload) as { sql?: string } | null
              return (
                <div key={c.call_index} style={stack(8)}>
                  <Num n={c.call_index + 1} label={<span style={mono}>{c.tool_name}</span>} />
                  <Code text={payload?.sql ?? c.payload} />
                </div>
              )
            })}
          </div>
        )}
      </Card>

      <Card title="Trace">
        <Trace raw={trace} />
      </Card>
    </div>
  )
}
