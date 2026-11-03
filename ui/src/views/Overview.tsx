import { useMemo, useState, type ReactNode } from 'react'
import { COST_NOTE } from '../components/CostInfo'
import { InfoLabel } from '../components/InfoLabel'
import { PageHeader } from '../components/PageHeader'
import { EvalLabel } from '../components/EvalLabel'
import {
  CHECKS,
  accuracyPasses,
  agentsOf,
  failedAnyRunNote,
  failingNote,
  errorReason,
  formatRunDate,
  formatRunTime,
  isError,
  meanOf,
  modelsOf,
  passedCell,
  passedRunsNote,
  passes,
  pct,
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
  type Check,
  type Run,
} from '../data/derive'
import type { ReportData, ResultRow } from '../data/types'
import { Badge, Card, DataTable, DateRangePicker, Heatmap, Icon, IconButton, ScoreCell, ScoreStat, Select, Tabs } from '../ds'
import { navigate } from '../router'
import { useNarrow } from '../useNarrow'

const PASSED_NOTE =
  "Evals that met both their accuracy and provenance min scores. An eval with no provenance min score only needs accuracy. Evals that stopped with an error aren't counted."

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

/** "3 evals failed accuracy or provenance min score · 1 stopped with an error". */
function failingSummary(run: Run) {
  const below = run.graded - run.passed
  const failed = `${below} ${below === 1 ? 'eval' : 'evals'} failed accuracy or provenance min score`
  return run.errored ? `${failed} · ${run.errored} stopped with an error` : failed
}

type PassCount = (run: Run) => { passed: number; of: number }
const PASSED: PassCount = (r) => ({ passed: r.passed, of: r.graded })
const ACCURACY_PASSED: PassCount = (r) => ({ passed: r.accuracyPassed, of: r.graded })
const PROVENANCE_PASSED: PassCount = (r) => ({ passed: r.provenancePassed, of: r.provenanceChecked })

/** A Passed card: the latest run's count big, its change in evals since the run before and its rate under it,
 * and the rate over the runs as a sparkline (a rate, so runs with more or fewer evals stay comparable).
 * Errored evals aren't counted; the card names them. */
function PassCard({ label, runs, count, unchecked }: { label: ReactNode; runs: Run[]; count: PassCount; unchecked?: string }) {
  const latest = runs[runs.length - 1]
  const { passed, of } = count(latest)
  const alert = latest.errored ? `${latest.errored} stopped with an error` : undefined
  if (latest.graded === 0) return <ScoreStat label={label} format="raw" value="—" caption="Every eval stopped with an error" />
  if (of === 0) return <ScoreStat label={label} format="raw" value="Not checked" caption={unchecked} alert={alert} />
  const before = runs.length > 1 ? count(runs[runs.length - 2]) : null
  const rates = runs.map(count).flatMap((c) => (c.of ? [c.passed / c.of] : []))
  return (
    <ScoreStat
      label={label}
      format="count"
      value={`${passed} / ${of}`}
      delta={before?.of ? passed - before.passed : undefined}
      caption={before ? pct(passed / of) : `First run in this range · ${pct(passed / of)}`}
      alert={alert}
      spark={rates.length > 1 ? rates : undefined}
    />
  )
}

/** The latest run's estimated cost, its change since the run before (a rise in red), and the cost over the runs
 * as a sparkline, scaled from 0 to the dearest run. */
function CostCard({ runs }: { runs: Run[] }) {
  const label = (
    <InfoLabel note={COST_NOTE} side="bottom">
      Est. cost
    </InfoLabel>
  )
  const latest = runs[runs.length - 1]
  const cost = runCost(latest)
  if (cost == null)
    return <ScoreStat label={label} format="raw" value="Not recorded" caption="A model without a price, or a run from before costs" />
  const before = runs.length > 1 ? runCost(runs[runs.length - 2]) : null
  const costs = runs.map(runCost).filter((c): c is number => c != null)
  return (
    <ScoreStat
      label={label}
      format="raw"
      value={usd(cost)}
      // Changes under a cent read as no change; the rest in whole cents.
      delta={before == null ? undefined : Math.abs(cost - before) < 0.01 ? 0 : cost - before}
      formatDelta={(d) => (d === 0 ? '±$0' : `${d > 0 ? '+' : '−'}$${Math.abs(d).toFixed(2)}`)}
      lowerIsBetter
      caption={runs.length > 1 ? undefined : 'First run in this range'}
      spark={costs.length > 1 ? costs : undefined}
      sparkRange={[0, Math.max(...costs)]}
    />
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
  const [metric, setMetric] = useState<Check>('accuracy')

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
  const categoryOf = new Map(evals.map((q) => [q.eval_id, q.category]))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageHeader title="Overview" subtitle={latest ? `Last eval run ${formatRunTime(latest.timestamp, { year: false })}` : undefined}>
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
            <Card>
              <PassCard label={<InfoLabel note={PASSED_NOTE} side="bottom">Passed</InfoLabel>} runs={runs} count={PASSED} />
            </Card>
            <Card>
              <PassCard label="Passed accuracy" runs={runs} count={ACCURACY_PASSED} />
            </Card>
            <Card>
              <PassCard
                label="Passed provenance"
                runs={runs}
                count={PROVENANCE_PASSED}
                unchecked="No eval in this run expects sources"
              />
            </Card>
            <Card>
              <CostCard runs={runs} />
            </Card>
          </div>

          <Card
            title="Scores by eval run"
            subtitle="Click a cell to see that answer"
            actions={<Tabs items={CHECKS} value={metric} onChange={(id) => setMetric(id as Check)} />}
          >
            <Heatmap
              metric={metric}
              showToggle={false}
              totalsLabel="Passed"
              totals={runs.map((run) => passedCell(run.results, metric))}
              totalsSummary={passedCell(runs.flatMap((run) => run.results), metric)}
              groupNote={(group, i) => {
                const inGroup = (results: ResultRow[]) => results.filter((r) => categoryOf.get(r.eval_id) === group)
                return i == null
                  ? failedAnyRunNote(inGroup(runs.flatMap((run) => run.results)), metric)
                  : failingNote(inGroup(runs[i].results), metric)
              }}
              rowNote={(row, i) => {
                if (i != null) return null
                const evalId = (row as ReturnType<typeof evalHeatRow>).eval_id
                return passedRunsNote(runs.flatMap((run) => run.results.filter((r) => r.eval_id === evalId)), metric)
              }}
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
