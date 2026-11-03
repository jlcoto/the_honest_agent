import { useMemo, useState } from 'react'
import { CostInfo } from '../components/CostInfo'
import { PageHeader } from '../components/PageHeader'
import { EvalLabel } from '../components/EvalLabel'
import {
  accuracyPasses,
  agentsOf,
  errorReason,
  formatRunDate,
  formatRunTime,
  isError,
  meanOf,
  modelsOf,
  passes,
  provenancePasses,
  evalHeatRow,
  evalTitles,
  evalsOf,
  resultsCost,
  runColumns,
  runCost,
  runsOf,
  smallUsd,
  stripMarkdown,
  toCsv,
  usd,
  type Run,
} from '../data/derive'
import type { ReportData, ResultRow } from '../data/types'
import { Badge, Card, DataTable, DateRangePicker, Heatmap, Icon, IconButton, ScoreCell, ScoreStat, Select, Tabs } from '../ds'
import { navigate } from '../router'
import { useNarrow } from '../useNarrow'

const METRICS = [
  { id: 'overall', label: 'Combined' },
  { id: 'accuracy', label: 'Accuracy' },
  { id: 'provenance', label: 'Provenance' },
]

const toneOf = (s: number) => (s >= 0.95 ? 'correct' : s >= 0.75 ? 'mostly' : s >= 0.4 ? 'partly' : 'wrong')
const openResult = (r: ResultRow) => navigate({ name: 'result', resultId: r.result_id })

function downloadCsv(filename: string, rows: ResultRow[], titles: Map<string, string>) {
  const csv = toCsv(
    ['eval_id', 'eval_title', 'category', 'accuracy_score', 'accuracy_min_score', 'provenance_score', 'provenance_min_score', 'failed', 'accuracy_method', 'expected_answer', 'agent_answer'],
    rows.map((r) => [
      r.eval_id,
      titles.get(r.eval_id) ?? null,
      r.category,
      r.accuracy_score,
      r.accuracy_min_score,
      r.provenance_score,
      r.provenance_min_score,
      isError(r) ? 'error' : [accuracyPasses(r) ? null : 'accuracy', provenancePasses(r) ? null : 'provenance'].filter(Boolean).join('+'),
      r.accuracy_method,
      r.expected_answer,
      r.agent_answer,
    ]),
  )
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  a.click()
  URL.revokeObjectURL(url)
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <Card>
      <div style={{ padding: '32px 0', textAlign: 'center', font: 'var(--type-body)', color: 'var(--fg-2)' }}>{children}</div>
    </Card>
  )
}

/** "Last eval run Oct 15, 12:47 · estimated cost $0.025 (i)"; the cost left out when the run has none. */
/** "2 below min score · 1 stopped with an error": errored evals have no scores, so they're
 * counted apart from the graded ones the stat shows. */
function passedCaption(run: Run) {
  const below = run.graded - run.passed
  const parts = [below ? `${below} below min score` : 'None below min score']
  if (run.errored) parts.push(`${run.errored} stopped with an error`)
  return parts.join(' · ')
}

/** "3 evals failed accuracy or provenance min score · 1 stopped with an error". */
function failingSummary(run: Run) {
  const below = run.graded - run.passed
  const failed = `${below} ${below === 1 ? 'eval' : 'evals'} failed accuracy or provenance min score`
  return run.errored ? `${failed} · ${run.errored} stopped with an error` : failed
}

/** The Overall or Accuracy card: the latest run's score, its change since the run before,
 * and a sparkline; runs where every eval stopped with an error have no score. */
function RunScore({ label, runs, pick }: { label: string; runs: Run[]; pick: (run: Run) => number | null }) {
  const value = pick(runs[runs.length - 1])
  const before = runs.length > 1 ? pick(runs[runs.length - 2]) : null
  if (value == null) return <ScoreStat label={label} format="raw" value="—" caption="Every eval stopped with an error" />
  return (
    <ScoreStat
      label={label}
      value={value}
      delta={before != null ? value - before : undefined}
      caption={runs.length > 1 ? undefined : 'First run in this range'}
      spark={runs.map(pick).filter((v): v is number => v != null)}
    />
  )
}

function LatestRun({ run }: { run: Run }) {
  const when = `Last eval run ${formatRunTime(run.timestamp, { year: false })}`
  const cost = runCost(run)
  if (cost == null) return when
  return (
    <>
      {when} · <CostInfo side="bottom">estimated cost {usd(cost)}</CostInfo>
    </>
  )
}

export function Overview({
  data,
  agent,
  setAgent,
}: {
  data: ReportData
  agent: string
  setAgent: (agent: string) => void
}) {
  const narrow = useNarrow()
  const allRuns = useMemo(() => runsOf(data.results), [data])
  const agents = useMemo(() => agentsOf(data.results), [data])
  const titles = useMemo(() => evalTitles(data.results), [data])
  const allDates = useMemo(() => [...new Set(allRuns.map((r) => r.date))], [allRuns])

  // Scores are only meaningful for one agent and one model at a time, so both
  // are always a single pick, defaulting to the latest run's. The agent comes from App.
  const agentRuns = allRuns.filter((r) => r.agent === agent)
  const models = modelsOf(agentRuns.flatMap((r) => r.results))
  const [modelPick, setModel] = useState(() => agentRuns.at(-1)?.model ?? '')
  const model = models.includes(modelPick) ? modelPick : (agentRuns.at(-1)?.model ?? '')
  const pairRuns = agentRuns.filter((r) => r.model === model)
  const [range, setRange] = useState(() => ({ from: allDates[0], to: allDates[allDates.length - 1] }))
  const [metric, setMetric] = useState<'overall' | 'accuracy' | 'provenance'>('overall')

  const switchAgent = (next: string) => {
    setAgent(next)
    setModel(allRuns.filter((r) => r.agent === next).at(-1)?.model ?? '')
  }
  const runs = pairRuns.filter((r) => r.date >= range.from && r.date <= range.to)

  if (allRuns.length === 0) {
    return (
      <>
        <PageHeader title="Overview" />
        <Empty>
          No results yet. Run <code>honest-agent run</code>, then <code>honest-agent report</code> again.
        </Empty>
      </>
    )
  }

  const latest = runs[runs.length - 1]
  const previous = runs[runs.length - 2]
  const failing = latest ? latest.results.filter((r) => !passes(r)) : []

  const columns = runColumns(runs)
  const evals = evalsOf(runs.flatMap((r) => r.results), titles)
  const resultsIn = (runIndex: number, evalId: string) => runs[runIndex].results.filter((r) => r.eval_id === evalId)
  const scoreIn = (runIndex: number, evalId: string, key: 'accuracy_score' | 'provenance_score') =>
    meanOf(resultsIn(runIndex, evalId).map((r) => r[key]))
  const heatRows = evals.map((q) =>
    evalHeatRow(
      q,
      runs.map((_, i) => scoreIn(i, q.eval_id, 'accuracy_score')),
      runs.map((_, i) => scoreIn(i, q.eval_id, 'provenance_score')),
      runs.map((_, i) => resultsCost(resultsIn(i, q.eval_id))),
    ),
  )
  const categories = [...new Set(evals.map((q) => q.category))]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageHeader title="Overview" subtitle={latest ? <LatestRun run={latest} /> : undefined}>
        <Select size="sm" icon="bot" options={agents} value={agent} onChange={switchAgent} />
        <Select size="sm" icon="cpu" options={models} value={model} onChange={setModel} />
        <DateRangePicker dates={[...new Set(pairRuns.map((r) => r.date))]} value={range} onChange={setRange} />
      </PageHeader>

      {!latest ? (
        <Empty>
          No eval runs of {agent} with {model} between {range.from} and {range.to}. Try a wider range.
        </Empty>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(200px, 100%), 1fr))', gap: 16 }}>
            {(['overall', 'accuracy'] as const).map((key) => (
              <Card key={key}>
                <RunScore label={key === 'overall' ? 'Overall' : 'Accuracy'} runs={runs} pick={(r) => r[key]} />
              </Card>
            ))}
            <Card>
              {latest.provenance == null ? (
                <ScoreStat label="Provenance" format="raw" value="Not checked" caption="No eval in this run expects sources" />
              ) : (
                <ScoreStat
                  label="Provenance"
                  value={latest.provenance}
                  delta={previous?.provenance != null ? latest.provenance - previous.provenance : undefined}
                  caption={previous ? undefined : 'First run in this range'}
                  spark={runs.map((r) => r.provenance).filter((v): v is number => v != null)}
                />
              )}
            </Card>
            <Card>
              <ScoreStat
                label="Passed thresholds"
                value={`${latest.passed} / ${latest.graded}`}
                format="raw"
                caption={passedCaption(latest)}
              />
            </Card>
          </div>

          <Card
            title="Scores by eval run"
            subtitle="Click a cell to see that answer"
            actions={<Tabs items={METRICS} value={metric} onChange={(id) => setMetric(id as typeof metric)} />}
          >
            <Heatmap
              metric={metric}
              showToggle={false}
              rowHeader="Eval"
              rowLabelWidth={narrow ? 150 : 360}
              groupBy="category"
              defaultExpanded={categories}
              rows={heatRows}
              columns={columns}
              formatCost={smallUsd}
              onCellClick={(row, column, value) => {
                const run = runs[columns.indexOf(column)]
                const evalId = (row as ReturnType<typeof evalHeatRow>).eval_id
                const result = value == null ? undefined : run?.results.find((r) => r.eval_id === evalId)
                if (result) openResult(result)
              }}
            />
          </Card>

          <Card
            title="Below threshold"
            subtitle={`Latest eval run, ${formatRunDate(latest.timestamp)} · ${failingSummary(latest)}`}
            actions={
              <IconButton
                icon="download"
                label="Export CSV"
                variant="secondary"
                size="sm"
                disabled={failing.length === 0}
                onClick={() => downloadCsv(`below-threshold-${latest.timestamp.slice(0, 10)}.csv`, failing, titles)}
              />
            }
          >
            {failing.length === 0 ? (
              <div style={{ padding: '28px 0', textAlign: 'center', font: 'var(--type-body)', color: 'var(--fg-2)' }}>
                Nothing to fix. Your agent was honest this run.
              </div>
            ) : (
              <DataTable
                rowKey="result_id"
                onRowClick={openResult}
                rows={failing}
                columns={[
                  {
                    key: 'eval_id',
                    label: 'Eval',
                    render: (r: ResultRow) => <EvalLabel evalId={r.eval_id} title={titles.get(r.eval_id)} />,
                  },
                  { key: 'category', label: 'Category' },
                  {
                    key: 'accuracy_score',
                    label: 'Accuracy',
                    render: (r: ResultRow) => <ScoreCell score={r.accuracy_score} threshold={r.accuracy_min_score ?? undefined} />,
                  },
                  {
                    key: 'provenance_score',
                    label: 'Provenance',
                    render: (r: ResultRow) => (
                      <ScoreCell score={r.provenance_score} threshold={r.provenance_min_score ?? undefined} />
                    ),
                  },
                  { key: 'accuracy_method', label: 'Method', render: (r: ResultRow) => <Badge mono>{r.accuracy_method}</Badge> },
                  {
                    key: 'expected_answer',
                    label: 'Expected',
                    mono: true,
                    // Numbers line up on the right; free-text expected answers stay left-aligned.
                    align: failing.every((r) => isNumeric(r.expected_answer)) ? 'right' : 'left',
                    render: (r: ResultRow) => truncate(r.expected_answer, 40),
                  },
                  {
                    key: 'agent_answer',
                    label: 'Agent said',
                    render: (r: ResultRow) => (
                      <span style={{ font: 'var(--type-small)', color: 'var(--fg-2)' }}>
                        {isError(r) ? errorReason(r) : answerPreview(r.agent_answer ?? '')}
                      </span>
                    ),
                  },
                  {
                    key: 'status',
                    label: '',
                    align: 'center',
                    // One pill per failed check, each coloured by its own score.
                    render: (r: ResultRow) => (
                      <span
                        style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4 }}
                      >
                        {isError(r) ? (
                          <Badge tone="wrong" dot>
                            Error
                          </Badge>
                        ) : null}
                        {isError(r) || accuracyPasses(r) ? null : (
                          <Badge tone={toneOf(r.accuracy_score ?? 0)} dot>
                            Accuracy
                          </Badge>
                        )}
                        {isError(r) || provenancePasses(r) ? null : (
                          <Badge tone={toneOf(r.provenance_score ?? 0)} dot>
                            Provenance
                          </Badge>
                        )}
                      </span>
                    ),
                  },
                  {
                    key: 'go',
                    label: '',
                    align: 'right',
                    width: 24,
                    render: () => (
                      <span style={{ display: 'inline-flex', color: 'var(--fg-3)' }}>
                        <Icon name="chevron-right" size={16} />
                      </span>
                    ),
                  },
                ]}
              />
            )}
          </Card>
        </>
      )}
    </div>
  )
}

const isNumeric = (s: string) => /^\s*[-+]?[\d,]*\.?\d+\s*$/.test(s)
// One line per row: paragraphs joined with " · " so "**0**\n\nThere were none." reads "0 · There were none."
const answerPreview = (s: string) =>
  truncate(s.split(/\n{2,}/).map(stripMarkdown).filter(Boolean).join(' · '), 90)
const truncate = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s)
