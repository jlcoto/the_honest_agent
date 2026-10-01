import { useMemo, useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { agentOf, agentsOf, bucketCounts, mean, modelsOf, quizHeatRow, quizTitles, quizzesOf, runsOf } from '../data/derive'
import type { ReportData, ResultRow } from '../data/types'
import { AccuracyBar, Card, DataTable, Heatmap, ScoreCell, Select, Tabs } from '../ds'
import { navigate } from '../router'

const METRICS = [
  { id: 'overall', label: 'Combined' },
  { id: 'accuracy', label: 'Accuracy' },
  { id: 'provenance', label: 'Provenance' },
]

interface ModelRow {
  model: string
  isCurrent: boolean
  runs: number
  latest: Map<string, ResultRow>
  accuracy: number
  provenance: number
  dAccuracy: number | null
  dProvenance: number | null
}

function Delta({ value }: { value: number | null }) {
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
    </span>
  )
}

export function Compare({ data }: { data: ReportData }) {
  const [metric, setMetric] = useState<'overall' | 'accuracy' | 'provenance'>('overall')
  const agents = useMemo(() => agentsOf(data.results), [data])
  // One agent at a time: models are only comparable on the same agent. Defaults to the latest run's.
  const [agent, setAgent] = useState(() => runsOf(data.results).at(-1)?.agent ?? '')

  const { rows, quizzes, current } = useMemo(() => {
    const results = data.results.filter((r) => agentOf(r) === agent)
    const runs = runsOf(results)
    const current = runs.length ? runs[runs.length - 1].model : null
    // Each model's most recent result per quiz (runs are sorted oldest first).
    const latestByModel = new Map<string, Map<string, ResultRow>>()
    for (const run of runs) {
      const latest = latestByModel.get(run.model) ?? new Map<string, ResultRow>()
      for (const r of run.results) latest.set(r.quiz_id, r)
      latestByModel.set(run.model, latest)
    }
    const base = current ? latestByModel.get(current)! : new Map<string, ResultRow>()
    const rows: ModelRow[] = modelsOf(results).map((model) => {
      const latest = latestByModel.get(model)!
      const results = [...latest.values()]
      const shared = [...latest.keys()].filter((q) => base.has(q))
      const sharedDelta = (key: 'accuracy_score' | 'provenance_score') =>
        model === current || shared.length === 0
          ? null
          : mean(shared.map((q) => latest.get(q)![key])) - mean(shared.map((q) => base.get(q)![key]))
      return {
        model,
        isCurrent: model === current,
        runs: runs.filter((r) => r.model === model).length,
        latest,
        accuracy: mean(results.map((r) => r.accuracy_score)),
        provenance: mean(results.map((r) => r.provenance_score)),
        dAccuracy: sharedDelta('accuracy_score'),
        dProvenance: sharedDelta('provenance_score'),
      }
    })
    return { rows, quizzes: quizzesOf(results, quizTitles(data.results)), current }
  }, [data, agent])


  const heatRows = quizzes.map((q) =>
    quizHeatRow(
      q,
      rows.map((m) => m.latest.get(q.quiz_id)?.accuracy_score ?? null),
      rows.map((m) => m.latest.get(q.quiz_id)?.provenance_score ?? null),
    ),
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageHeader
        title="Model comparison"
        subtitle={`${agent} · ${rows.length} models · each model's latest result per quiz`}
      >
        <Select size="sm" icon="bot" options={agents} value={agent} onChange={setAgent} />
      </PageHeader>
      {rows.length === 0 ? (
        <Card>
          <p style={{ margin: 0, padding: '24px 0', textAlign: 'center', font: 'var(--type-body)', color: 'var(--fg-2)' }}>
            No results yet. Run <code>agent-quiz run</code>, then <code>agent-quiz report</code> again.
          </p>
        </Card>
      ) : (
        <>
          <Card
            title="Results by model"
            subtitle={`Differences in points vs the current model, ${current}, on the quizzes both ran`}
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
                      <span style={{ font: '500 13px var(--font-mono)', whiteSpace: 'nowrap' }}>{r.model}</span>
                      {r.isCurrent ? (
                        <span style={{ font: '400 12px var(--font-sans)', color: 'var(--fg-3)' }}>Current model (latest run)</span>
                      ) : null}
                    </span>
                  ),
                },
                {
                  key: 'coverage',
                  label: 'Quizzes',
                  render: (r: ModelRow) => (
                    <span style={{ font: '400 13px var(--font-mono)', color: 'var(--fg-2)', whiteSpace: 'nowrap' }}>
                      {r.latest.size} of {quizzes.length} · {r.runs} {r.runs === 1 ? 'run' : 'runs'}
                    </span>
                  ),
                },
                {
                  key: 'accuracy',
                  label: 'Accuracy',
                  render: (r: ModelRow) => (
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <ScoreCell score={r.accuracy} />
                      <Delta value={r.dAccuracy} />
                    </span>
                  ),
                },
                {
                  key: 'provenance',
                  label: 'Provenance',
                  render: (r: ModelRow) => (
                    <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <ScoreCell score={r.provenance} />
                      <Delta value={r.dProvenance} />
                    </span>
                  ),
                },
                {
                  key: 'mix',
                  label: 'Answer mix',
                  width: 180,
                  render: (r: ModelRow) => (
                    <AccuracyBar counts={bucketCounts([...r.latest.values()].map((x) => x.accuracy_score))} height={8} />
                  ),
                },
              ]}
            />
          </Card>
          <Card
            title="Scores by model"
            subtitle="Grey cells: that model never ran the quiz · click a cell to see the answer"
            actions={<Tabs items={METRICS} value={metric} onChange={(id) => setMetric(id as typeof metric)} />}
          >
            <Heatmap
              metric={metric}
              showToggle={false}
              showSummary={false}
              rowHeader="Quiz"
              rowLabelWidth={360}
              groupBy="category"
              defaultExpanded={[...new Set(quizzes.map((q) => q.category))]}
              rows={heatRows}
              columns={rows.map((m) => m.model)}
              cellWidth={56}
              onCellClick={(row, column) => {
                const quizId = (row as ReturnType<typeof quizHeatRow>).quiz_id
                const result = rows.find((m) => m.model === column)?.latest.get(quizId)
                if (result) navigate({ name: 'result', resultId: result.result_id })
              }}
            />
          </Card>
        </>
      )}
    </div>
  )
}
