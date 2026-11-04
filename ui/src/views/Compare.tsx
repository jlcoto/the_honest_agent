import { useMemo, useState } from 'react'
import { asLabel } from '../components/asLabel'
import { CostInfo } from '../components/CostInfo'
import { InfoLabel } from '../components/InfoLabel'
import { PageHeader } from '../components/PageHeader'
import { SCORES_OVER_TIME_NOTE, ScoresOverTime, seriesColors } from '../components/ScoresOverTime'
import {
  CHECKS,
  accuracyPasses,
  agentOf,
  agentsOf,
  evalHeatRow,
  evalTitles,
  evalsOf,
  passedLines,
  formatRunTime,
  isError,
  passedCell,
  passes,
  pct,
  provenanceChecked,
  provenancePasses,
  resultsCost,
  runCost,
  runsOf,
  smallUsd,
  usd,
  type Check,
  type Run,
} from '../data/derive'
import type { ReportData, ResultRow } from '../data/types'
import { Badge, Card, DataTable, DateRangePicker, Heatmap, Icon, Select, Tabs, Tooltip } from '../ds'
import { navigate } from '../router'
import { useNarrow } from '../useNarrow'

/** A Passed column: which evals it checks, and whether one passed. */
const PASS_CHECKS = {
  passed: { checks: (r: ResultRow) => !isError(r), passes },
  accuracy: { checks: (r: ResultRow) => !isError(r), passes: accuracyPasses },
  provenance: { checks: provenanceChecked, passes: provenancePasses },
}
type PassKey = keyof typeof PASS_CHECKS

interface PassCount {
  passed: number
  /** Evals this check covers in the selected run. */
  of: number
  /** Change in passing evals vs the baseline, over the shared evals both runs checked; null for the baseline. */
  delta: number | null
}

interface ModelRow {
  model: string
  isBaseline: boolean
  /** The model's runs, newest first; the dropdown lists them. */
  runs: Run[]
  /** The run this row shows: the latest unless another was picked. */
  run: Run
  isLatest: boolean
  /** The selected run's results by eval_id. */
  latest: Map<string, ResultRow>
  /** The selected run's Passed, Passed accuracy and Passed provenance, as on the Overview. */
  counts: Record<PassKey, PassCount>
  /** Evals both this model's and the baseline's selected runs contain; the differences are computed on these. */
  shared: number
  /** Not the baseline, and its selected run shares no evals with the baseline's, so there's no difference to show. */
  noOverlap: boolean
  /** Not the baseline, and its selected run tested a different set of evals than the baseline's. */
  differs: boolean
}

/** Why a row's run isn't comparable with the baseline's, by how its evals overlap the baseline's. */
function differsNote(shared: number, baselineEvals: number) {
  const overlap =
    shared === 0
      ? `Shares none of the ${baselineEvals} baseline evals.`
      : shared < baselineEvals
        ? `Shares only ${shared} of ${baselineEvals} baseline evals.`
        : "Also tested evals the baseline didn't."
  return `${overlap} For fully comparable results, rerun on the same evals.`
}


function Delta({ value, shared, noOverlap }: { value: number | null; shared: number; noOverlap: boolean }) {
  if (noOverlap) return <span style={{ font: '400 12px var(--font-sans)', color: 'var(--fg-3)' }}>no evals in common</span>
  if (value == null) return null
  return (
    <span
      style={{
        font: '500 12px var(--font-mono)',
        whiteSpace: 'nowrap',
        color: value === 0 ? 'var(--fg-3)' : value > 0 ? 'var(--acc-correct-ink)' : 'var(--acc-wrong-ink)',
      }}
    >
      {value === 0 ? '±0' : `${value > 0 ? '+' : '−'}${Math.abs(value)}`}
      <span style={{ font: '400 12px var(--font-sans)', color: 'var(--fg-3)' }}> · {shared} shared</span>
    </span>
  )
}

/** A Passed cell: the count, the rate under it, and the difference from the baseline. */
function PassCell({ row, pass, unchecked }: { row: ModelRow; pass: PassKey; unchecked?: string }) {
  const { passed, of, delta } = row.counts[pass]
  const sub = { font: '400 12px var(--font-sans)', color: 'var(--fg-3)' }
  if (of === 0)
    return (
      <span style={{ font: '400 13px var(--font-mono)', color: 'var(--fg-3)' }}>
        — <span style={{ font: 'var(--type-small)' }}>{row.run.graded ? unchecked : 'every eval stopped with an error'}</span>
      </span>
    )
  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 2, whiteSpace: 'nowrap' }}>
      <span style={{ font: '500 13px var(--font-mono)' }}>
        {passed} / {of}
      </span>
      <span style={sub}>{pct(passed / of)}</span>
      <Delta value={delta} shared={row.shared} noOverlap={row.noOverlap} />
    </span>
  )
}

/** The run's estimated cost, and what that comes to per eval under it. */
function CostCell({ run, evals }: { run: Run; evals: number }) {
  const total = runCost(run)
  if (total == null)
    return (
      <span style={{ font: '400 13px var(--font-mono)', color: 'var(--fg-3)' }}>
        — <span style={{ font: 'var(--type-small)' }}>not recorded</span>
      </span>
    )
  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 2, whiteSpace: 'nowrap' }}>
      <span style={{ font: '500 13px var(--font-mono)' }}>{usd(total)}</span>
      <span style={{ font: '400 12px var(--font-sans)', color: 'var(--fg-3)' }}>{smallUsd(total / evals)} per eval</span>
    </span>
  )
}

export function Compare({
  data,
  agent,
  setAgent,
}: {
  data: ReportData
  agent: string
  setAgent: (agent: string) => void
}) {
  const narrow = useNarrow()
  const [metric, setMetric] = useState<Check>('accuracy')
  const [trendMetric, setTrendMetric] = useState<Check>('accuracy')
  const agents = useMemo(() => agentsOf(data.results), [data])
  const agentRuns = useMemo(() => runsOf(data.results.filter((r) => agentOf(r) === agent)), [data, agent])
  // One color per model for the whole report, independent of agent, date range or baseline.
  const modelColors = useMemo(() => seriesColors(runsOf(data.results)), [data])
  // Only runs in this range count, so the page can go back in time. Defaults to every run, as on the Overview.
  const allDates = useMemo(() => [...new Set(runsOf(data.results).map((r) => r.date))].sort(), [data])
  const [range, setRange] = useState(() => ({ from: allDates[0], to: allDates[allDates.length - 1] }))
  // Picked run_id per model, defaulting to each model's latest run. Kept per agent so switching agent resets it.
  const [picks, setPicks] = useState<{ agent: string; runs: Record<string, string> }>({ agent, runs: {} })
  const picked = picks.agent === agent ? picks.runs : {}
  const pick = (model: string, runId: string) => setPicks({ agent, runs: { ...picked, [model]: runId } })
  // One agent at a time: models are only comparable on the same agent. The agent comes from App.
  const { rows, evals, baseline } = useMemo(() => {
    const runs = agentRuns.filter((r) => r.date >= range.from && r.date <= range.to)
    // Each model's runs, newest first (runsOf sorts oldest first). A row shows one run, so its numbers share one date.
    const runsByModel = new Map<string, Run[]>()
    for (const run of [...runs].reverse()) runsByModel.set(run.model, [...(runsByModel.get(run.model) ?? []), run])
    const selectedRun = (model: string) => {
      const modelRuns = runsByModel.get(model)!
      return modelRuns.find((r) => r.run_id === picked[model]) ?? modelRuns[0]
    }
    // The baseline is the model of the agent's most recent run in the range; differences are measured against its selected run.
    const baseline = runs.length ? runs[runs.length - 1].model : null
    const resultsOf = (model: string) => new Map(selectedRun(model).results.map((r) => [r.eval_id, r]))
    const base = baseline ? resultsOf(baseline) : new Map<string, ResultRow>()
    // Baseline first, then the rest by name.
    const models = [...runsByModel.keys()].sort((x, y) => Number(y === baseline) - Number(x === baseline) || x.localeCompare(y))
    const rows: ModelRow[] = models.map((model) => {
      const latest = resultsOf(model)
      const shared = [...latest.keys()].filter((q) => base.has(q))
      // Over the shared evals both runs checked: an error or a provenance check on one side only is left out.
      const countOf = (pass: PassKey): PassCount => {
        const { checks, passes } = PASS_CHECKS[pass]
        const checked = [...latest.values()].filter(checks)
        const both = shared.filter((q) => checks(latest.get(q)!) && checks(base.get(q)!))
        const passing = (results: Map<string, ResultRow>) => both.filter((q) => passes(results.get(q)!)).length
        return {
          passed: checked.filter(passes).length,
          of: checked.length,
          delta: model === baseline || both.length === 0 ? null : passing(latest) - passing(base),
        }
      }
      return {
        model,
        isBaseline: model === baseline,
        runs: runsByModel.get(model)!,
        run: selectedRun(model),
        isLatest: selectedRun(model) === runsByModel.get(model)![0],
        latest,
        counts: { passed: countOf('passed'), accuracy: countOf('accuracy'), provenance: countOf('provenance') },
        shared: shared.length,
        noOverlap: model !== baseline && shared.length === 0,
        differs: model !== baseline && !(shared.length === base.size && latest.size === base.size),
      }
    })
    const selectedResults = models.flatMap((model) => selectedRun(model).results)
    return { rows, evals: evalsOf(selectedResults, evalTitles(data.results)), baseline }
  }, [data, agentRuns, range, picked])

  const heatRows = evals.map((q) =>
    evalHeatRow(
      q,
      rows.map((m) => m.latest.get(q.eval_id)?.accuracy_score ?? null),
      rows.map((m) => m.latest.get(q.eval_id)?.provenance_score ?? null),
      rows.map((m) => {
        const result = m.latest.get(q.eval_id)
        return result ? resultsCost([result]) : null
      }),
    ),
  )

  const baselineEvals = rows.find((m) => m.isBaseline)?.latest.size ?? 0
  const categoryOf = new Map(evals.map((q) => [q.eval_id, q.category]))
  // Heatmap column per model; which run each shows is in the Results table above (rotated headers can't fit a date).
  const columns = rows.map((m) => m.model)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageHeader
        title="Model comparison"
        subtitle={`${agent} · ${rows.length} ${rows.length === 1 ? 'model' : 'models'} · latest run per model unless you pick another`}
      >
        <Select size="sm" icon="bot" options={agents} value={agent} onChange={setAgent} />
        <DateRangePicker dates={[...new Set(agentRuns.map((r) => r.date))]} value={range} onChange={setRange} />
      </PageHeader>
      {rows.length === 0 ? (
        <Card>
          <p style={{ margin: 0, padding: '24px 0', textAlign: 'center', font: 'var(--type-body)', color: 'var(--fg-2)' }}>
            {agentRuns.length ? (
              <>
                No eval runs of {agent} between {range.from} and {range.to}. Try a wider range.
              </>
            ) : (
              <>
                No results yet. Run <code>honest-agent run</code>, then <code>honest-agent report</code> again.
              </>
            )}
          </p>
        </Card>
      ) : (
        <>
          <Card
            title="Results by model"
            subtitle={asLabel(
              <span>
                Differences in evals vs the baseline, {baseline}, on the evals both ran ·{' '}
                <CostInfo side="bottom">costs are estimates</CostInfo>
              </span>,
            )}
          >
            <DataTable
              rowKey="model"
              rows={rows}
              columns={[
                {
                  key: 'model',
                  label: 'Model',
                  render: (r: ModelRow) => (
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ font: '500 13px var(--font-mono)', whiteSpace: 'nowrap' }}>{r.model}</span>
                        {r.differs ? (
                          // Opens upward: the table clips below its last row, and the baseline row is always above this one.
                          <Tooltip
                            side="top"
                            content={
                              <span style={{ display: 'block', width: 240, whiteSpace: 'normal' }}>
                                {differsNote(r.shared, baselineEvals)}
                              </span>
                            }
                          >
                            <span
                              role="img"
                              aria-label={differsNote(r.shared, baselineEvals)}
                              tabIndex={0}
                              style={{ display: 'inline-flex', color: 'var(--fg-3)', cursor: 'help' }}
                            >
                              <Icon name="info" size={14} />
                            </span>
                          </Tooltip>
                        ) : null}
                      </span>
                      {r.isBaseline ? (
                        <span>
                          <Badge>Baseline</Badge>
                        </span>
                      ) : null}
                    </span>
                  ),
                },
                {
                  key: 'run',
                  label: 'Run',
                  render: (r: ModelRow) => (
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2, whiteSpace: 'nowrap' }}>
                      {r.runs.length > 1 ? (
                        // Wrapped so the column's flex layout doesn't stretch the Select away from its arrow.
                        <span style={{ alignSelf: 'flex-start' }}>
                          <Select
                            size="sm"
                            value={r.run.run_id}
                            onChange={(runId) => pick(r.model, runId)}
                            options={r.runs.map((run, i) => ({
                              value: run.run_id,
                              label: `${formatRunTime(run.timestamp)}${i === 0 ? ' (latest)' : ''}`,
                            }))}
                          />
                        </span>
                      ) : (
                        <span style={{ font: '400 13px var(--font-mono)' }}>{formatRunTime(r.run.timestamp)}</span>
                      )}
                      <span style={{ font: '400 12px var(--font-sans)', color: 'var(--fg-3)' }}>
                        {r.latest.size} {r.latest.size === 1 ? 'eval' : 'evals'}
                        {r.isLatest ? '' : ' · older run'}
                      </span>
                      {/* Under the run, not a count: it's the same for every Passed column and would push one out of line. */}
                      {r.run.errored ? (
                        <span style={{ font: '400 12px var(--font-sans)', color: 'var(--acc-wrong-ink)' }}>
                          {r.run.errored} stopped with an error
                        </span>
                      ) : null}
                    </span>
                  ),
                },
                {
                  key: 'cost',
                  label: 'Est. cost',
                  render: (r: ModelRow) => <CostCell run={r.run} evals={r.latest.size} />,
                },
                { key: 'passed', label: 'Passed', render: (r: ModelRow) => <PassCell row={r} pass="passed" /> },
                { key: 'accuracy', label: 'Passed accuracy', render: (r: ModelRow) => <PassCell row={r} pass="accuracy" /> },
                {
                  key: 'provenance',
                  label: 'Passed provenance',
                  render: (r: ModelRow) => <PassCell row={r} pass="provenance" unchecked="not checked" />,
                },
              ]}
            />
          </Card>
          <Card
            title="Scores by model"
            subtitle="Each model's selected run · grey cells: not in that run, or stopped with an error · click a cell to see the answer"
            actions={<Tabs items={CHECKS} value={metric} onChange={(id) => setMetric(id as Check)} />}
          >
            <Heatmap
              metric={metric}
              showToggle={false}
              showSummary={false}
              totalsLabel="Passed"
              totals={rows.map((m) => passedCell(m.run.results, metric))}
              groupLines={(group, i) =>
                i == null ? null : passedLines(rows[i].run.results.filter((r) => categoryOf.get(r.eval_id) === group), metric)
              }
              rowHeader="Eval"
              rowLabelWidth={narrow ? 150 : 360}
              groupBy="category"
              defaultExpanded={[...new Set(evals.map((q) => q.category))]}
              rows={heatRows}
              columns={columns}
              formatCost={smallUsd}
              cellWidth={56}
              onCellClick={(row, column) => {
                const evalId = (row as ReturnType<typeof evalHeatRow>).eval_id
                const result = rows[columns.indexOf(column)]?.latest.get(evalId)
                if (result) navigate({ name: 'result', resultId: result.result_id })
              }}
            />
          </Card>
          <Card
            title="Scores over time"
            subtitle={asLabel(
              <span>
                One row per model · each point is the model's last{' '}
                <InfoLabel note={SCORES_OVER_TIME_NOTE} side="bottom">
                  run that day
                </InfoLabel>
              </span>,
            )}
            actions={<Tabs items={CHECKS} value={trendMetric} onChange={(id) => setTrendMetric(id as Check)} />}
          >
            {/* All runs in the date range, regardless of the Run dropdowns: this card is the history. */}
            <ScoresOverTime
              runs={agentRuns.filter((r) => r.date >= range.from && r.date <= range.to)}
              models={rows.map((m) => m.model)}
              metric={trendMetric}
              colors={modelColors}
            />
          </Card>
        </>
      )}
    </div>
  )
}
