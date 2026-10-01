import type { CSSProperties, ReactNode } from 'react'
import { PageHeader } from '../components/PageHeader'
import { accuracyPasses, agentOf, formatRunTime, pct, provenancePasses, quizTitles, toolCallsFor } from '../data/derive'
import type { ReportData } from '../data/types'
import { Badge, Button, Card, ScoreStat } from '../ds'

const codeBlock: CSSProperties = {
  margin: 0,
  padding: '10px 12px',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--bg-sunken)',
  border: '1px solid var(--border-1)',
  font: 'var(--type-data)',
  color: 'var(--fg-1)',
  whiteSpace: 'pre-wrap',
  overflowWrap: 'anywhere',
}
const label: CSSProperties = { font: 'var(--type-label)', color: 'var(--fg-2)' }
const prose: CSSProperties = { margin: 0, font: 'var(--type-body)', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }

function Field({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      <span style={label}>{name}</span>
      {children}
    </div>
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

function TraceBlock({ block }: { block: Block }) {
  if (block.type === 'text') return <p style={prose}>{block.text}</p>
  if (block.type === 'tool_use') {
    const input = block.input as { sql?: unknown } | undefined
    return (
      <Field name={`Tool call · ${block.name}`}>
        <pre style={codeBlock}>{typeof input?.sql === 'string' ? input.sql : JSON.stringify(block.input, null, 2)}</pre>
      </Field>
    )
  }
  if (block.type === 'tool_result') {
    const content = Array.isArray(block.content)
      ? block.content.map((c: Block) => c.text ?? JSON.stringify(c)).join('\n')
      : String(block.content ?? '')
    return (
      <Field name={block.is_error ? 'Tool error' : 'Tool result'}>
        <pre style={{ ...codeBlock, color: block.is_error ? 'var(--acc-wrong-ink)' : 'var(--fg-1)' }}>{content}</pre>
      </Field>
    )
  }
  return <pre style={codeBlock}>{JSON.stringify(block, null, 2)}</pre>
}

function Trace({ raw }: { raw: string | undefined }) {
  const messages = raw ? parseJson(raw) : null
  if (!Array.isArray(messages)) return <pre style={codeBlock}>{raw ?? 'No trace recorded.'}</pre>
  return (
    <ol style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 16 }}>
      {messages.map((m: { role?: string; content?: unknown }, i: number) => (
        <li key={i} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span style={{ ...label, textTransform: 'capitalize' }}>
            {i + 1}. {m.role}
          </span>
          {typeof m.content === 'string' ? (
            <p style={prose}>{m.content}</p>
          ) : (
            (Array.isArray(m.content) ? m.content : []).map((b: Block, j: number) => <TraceBlock key={j} block={b} />)
          )}
        </li>
      ))}
    </ol>
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
  const title = quizTitles(data.results).get(r.quiz_id)
  const context = `${r.category ?? 'Uncategorized'} · ${formatRunTime(r.run_timestamp)} · ${agentOf(r)} · ${r.model_name}`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageHeader
        title={title ?? <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>{r.quiz_id}</span>}
        subtitle={
          title ? (
            <>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{r.quiz_id}</span> · {context}
            </>
          ) : (
            context
          )
        }
      >
        <Badge tone={accOk ? 'correct' : 'wrong'} dot>
          Accuracy {accOk ? 'passed' : 'below min'}
        </Badge>
        <Badge tone={provOk ? 'correct' : 'wrong'} dot>
          Provenance {provOk ? 'passed' : 'below min'}
        </Badge>
        {back}
      </PageHeader>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16 }}>
        <Card>
          <ScoreStat label="Accuracy" value={r.accuracy_score} caption={`min score ${pct(r.accuracy_min_score)}`} />
        </Card>
        <Card>
          <ScoreStat label="Provenance" value={r.provenance_score} caption={`min score ${pct(r.provenance_min_score)}`} />
        </Card>
        <Card>
          <ScoreStat
            label="Latency"
            format="raw"
            value={r.latency_ms == null ? '—' : `${(r.latency_ms / 1000).toFixed(1)}s`}
            caption="Agent run, excluding grading"
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
              caption={`${(r.agent_input_tokens ?? 0).toLocaleString('en-US')} in · ${(r.agent_output_tokens ?? 0).toLocaleString('en-US')} out`}
            />
          )}
        </Card>
      </div>

      <Card title="Answer">
        <Field name="Prompt">
          <p style={prose}>{r.prompt}</p>
        </Field>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16 }}>
          <Field name="Expected">
            <pre style={codeBlock}>{r.expected_answer}</pre>
          </Field>
          <Field name="Agent said">
            <pre style={{ ...codeBlock, fontFamily: 'var(--font-sans)' }}>{r.agent_answer || '(empty answer)'}</pre>
          </Field>
        </div>
        <Field name="Grading">
          <span style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: 8 }}>
            <Badge mono>{r.accuracy_method}</Badge>
            <span style={{ font: 'var(--type-small)', color: 'var(--fg-2)' }}>{r.accuracy_rationale ?? 'No rationale recorded.'}</span>
          </span>
        </Field>
      </Card>

      <Card title="Provenance" subtitle="Which tables the quiz expected the agent to query, and what it used">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
          <Field name="Expected sources">
            <Ids ids={r.expected_sources} />
          </Field>
          <Field name="Expected database / schema">
            <span style={{ font: 'var(--type-data)' }}>
              {r.expected_database ?? '—'} / {r.expected_schema ?? '—'}
            </span>
          </Field>
          <Field name="Tools used">
            <Ids ids={r.tools_used} />
          </Field>
        </div>
      </Card>

      <Card title={`SQL calls (${calls.length})`} subtitle="Every SQL statement captured from the agent's tool calls, in order">
        {calls.length === 0 ? (
          <p style={{ margin: 0, font: 'var(--type-small)', color: 'var(--fg-3)' }}>No SQL was captured for this answer.</p>
        ) : (
          calls.map((c) => {
            const payload = parseJson(c.payload) as { sql?: string } | null
            return (
              <Field key={c.call_index} name={`${c.call_index + 1}. ${c.tool_name}`}>
                <pre style={codeBlock}>{payload?.sql ?? c.payload}</pre>
              </Field>
            )
          })
        )}
      </Card>

      <Card title="Trace" subtitle="The agent's full turn-by-turn conversation, including tool calls and results">
        <Trace raw={trace} />
      </Card>
    </div>
  )
}
