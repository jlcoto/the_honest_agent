import { useMemo, useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { agentOf, agentsOf, evalHeatRow, evalTitles, evalsOf, formatRunTime, mean, runsOf, type Run } from '../data/derive'
import type { ReportData, ResultRow } from '../data/types'
import { AccuracyBar, Badge, Card, DataTable, Heatmap, Icon, ScoreCell, Select, Tabs, Tooltip } from '../ds'
import { navigate } from '../router'

const METRICS = [
  { id: 'overall', label: 'Combined' },
  { id: 'accuracy', label: 'Accuracy' },
  { id: 'provenance', label: 'Provenance' },
]

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
  accuracy: number
  provenance: number
  dAccuracy: number | null
  dProvenance: number | null
  /** Evals both this model's and the baseline's selected runs contain; the differences are computed on these. */
  shared: number
  /** Evals in the selected run that met both their accuracy and provenance thresholds, as on the Overview. */
  passed: number
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
  const flat = Math.abs(value) < 0.0005
  return (
    <span
      style={{
        font: '500 12px var(--font-mono)',
        whiteSpace: 'nowrap',
        color: flat ? 'var(--fg-3)' : value > 0 ? 'var(--acc-correct-ink)' : 'var(--acc-wrong-ink)',
      }}
    >
      {flat ? '±0.0 pp' : `${value > 0 ? '+' : '−'}${Math.abs(value * 100).toFixed(1)} pp`}
      <span style={{ font: '400 12px var(--font-sans)', color: 'var(--fg-3)' }}> · {shared} shared</span>
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
  const [metric, setMetric] = useState<'overall' | 'accuracy' | 'provenance'>('overall')
  const agents = useMemo(() => agentsOf(data.results), [data])
  // Picked run_id per model, defaulting to each model's latest run. Kept per agent so switching agent resets it.
  const [picks, setPicks] = useState<{ agent: string; runs: Record<string, string> }>({ agent, runs: {} })
  const picked = picks.agent === agent ? picks.runs : {}
  const pick = (model: string, runId: string) => setPicks({ agent, runs: { ...picked, [model]: runId } })
  // One agent at a time: models are only comparable on the same agent. The agent comes from App.
  const { rows, evals, baseline } = useMemo(() => {
    const runs = runsOf(data.results.filter((r) => agentOf(r) === agent))
    // Each model's runs, newest first (runsOf sorts oldest first). A row shows one run, so its numbers share one date.
    const runsByModel = new Map<string, Run[]>()
    for (const run of [...runs].reverse()) runsByModel.set(run.model, [...(runsByModel.get(run.model) ?? []), run])
    const selectedRun = (model: string) => {
      const modelRuns = runsByModel.get(model)!
      return modelRuns.find((r) => r.run_id === picked[model]) ?? modelRuns[0]
    }
    // The baseline is the model of the agent's most recent run; differences are measured against its selected run.
    const baseline = runs.length ? runs[runs.length - 1].model : null
    const resultsOf = (model: string) => new Map(selectedRun(model).results.map((r) => [r.eval_id, r]))
    const base = baseline ? resultsOf(baseline) : new Map<string, ResultRow>()
    // Baseline first, then the rest by name.
    const models = [...runsByModel.keys()].sort((x, y) => Number(y === baseline) - Number(x === baseline) || x.localeCompare(y))
    const rows: ModelRow[] = models.map((model) => {
      const latest = resultsOf(model)
      const results = [...latest.values()]
      const shared = [...latest.keys()].filter((q) => base.has(q))
      const sharedDelta = (key: 'accuracy_score' | 'provenance_score') =>
        model === baseline || shared.length === 0
          ? null
          : mean(shared.map((q) => latest.get(q)![key])) - mean(shared.map((q) => base.get(q)![key]))
      return {
        model,
        isBaseline: model === baseline,
        runs: runsByModel.get(model)!,
        run: selectedRun(model),
        isLatest: selectedRun(model) === runsByModel.get(model)![0],
        latest,
        accuracy: mean(results.map((r) => r.accuracy_score)),
        provenance: mean(results.map((r) => r.provenance_score)),
        dAccuracy: sharedDelta('accuracy_score'),
        dProvenance: sharedDelta('provenance_score'),
        shared: shared.length,
        passed: selectedRun(model).passed,
        noOverlap: model !== baseline && shared.length === 0,
        differs: model !== baseline && !(shared.length === base.size && latest.size === base.size),
      }
    })
    const selectedResults = models.flatMap((model) => selectedRun(model).results)
    return { rows, evals: evalsOf(selectedResults, evalTitles(data.results)), baseline }
  }, [data, agent, picked])

  const heatRows = evals.map((q) =>
    evalHeatRow(
      q,
      rows.map((m) => m.latest.get(q.eval_id)?.accuracy_score ?? null),
      rows.map((m) => m.latest.get(q.eval_id)?.provenance_score ?? null),
    ),
  )

  const baselineEvals = rows.find((m) => m.isBaseline)?.latest.size ?? 0
  // Heatmap column per model; a picked older run gets its date so the column says which run it shows.
  const columns = rows.map((m) => (m.isLatest ? m.model : `${m.model} · ${formatRunTime(m.run.timestamp, { year: false })}`))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageHeader
        title="Model comparison"
        subtitle={`${agent} · ${rows.length} ${rows.length === 1 ? 'model' : 'models'} · latest run per model unless you pick another`}
      >
        <Select size="sm" icon="bot" options={agents} value={agent} onChange={setAgent} />
      </PageHeader>
      {rows.length === 0 ? (
        <Card>
          <p style={{ margin: 0, padding: '24px 0', textAlign: 'center', font: 'var(--type-body)', color: 'var(--fg-2)' }}>
            No results yet. Run <code>honest-agent run</code>, then <code>honest-agent report</code> again.
          </p>
        </Card>
      ) : (
        <>
          <Card
            title="Results by model"
            subtitle={`Differences in points vs the baseline, ${baseline}, on the evals both ran`}
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
                    </span>
                  ),
                },
                {
                  key: 'accuracy',
                  label: 'Accuracy',
                  render: (r: ModelRow) => (
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <ScoreCell score={r.accuracy} />
                      <Delta value={r.dAccuracy} shared={r.shared} noOverlap={r.noOverlap} />
                    </span>
                  ),
                },
                {
                  key: 'provenance',
                  label: 'Provenance',
                  render: (r: ModelRow) => (
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <ScoreCell score={r.provenance} />
                      <Delta value={r.dProvenance} shared={r.shared} noOverlap={r.noOverlap} />
                    </span>
                  ),
                },
                {
                  key: 'passed',
                  label: 'Passed thresholds',
                  width: 200,
                  render: (r: ModelRow) => (
                    <span
                      style={{ display: 'block', padding: '6px 0' }}
                      title={`${r.passed} of ${r.latest.size} passed · ${r.latest.size - r.passed} below min score`}
                    >
                      {/* pointerEvents off so the bar's own segment titles ("Correct"/"Wrong") don't replace this one. */}
                      <span style={{ display: 'block', pointerEvents: 'none' }}>
                        <AccuracyBar counts={{ correct: r.passed, wrong: r.latest.size - r.passed }} height={8} />
                      </span>
                    </span>
                  ),
                },
              ]}
            />
          </Card>
          <Card
            title="Scores by model"
            subtitle="Each model's selected run · grey cells: not in that run · click a cell to see the answer"
            actions={<Tabs items={METRICS} value={metric} onChange={(id) => setMetric(id as typeof metric)} />}
          >
            <Heatmap
              metric={metric}
              showToggle={false}
              showSummary={false}
              rowHeader="Eval"
              rowLabelWidth={360}
              groupBy="category"
              defaultExpanded={[...new Set(evals.map((q) => q.category))]}
              rows={heatRows}
              columns={columns}
              cellWidth={56}
              onCellClick={(row, column) => {
                const evalId = (row as ReturnType<typeof evalHeatRow>).eval_id
                const result = rows[columns.indexOf(column)]?.latest.get(evalId)
                if (result) navigate({ name: 'result', resultId: result.result_id })
              }}
            />
          </Card>
        </>
      )}
    </div>
  )
}
