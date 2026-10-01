import { useMemo, useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { formatRunTime, mean, modelsOf, passes, accuracyPasses, quizzesOf, runColumns, runsOf } from '../data/derive'
import type { ReportData, ResultRow } from '../data/types'
import { Badge, Card, DataTable, DateRangePicker, Heatmap, ScoreCell, ScoreStat, Select, Tabs } from '../ds'
import { navigate } from '../router'

const ALL_MODELS = 'All models'
const METRICS = [
  { id: 'overall', label: 'Combined' },
  { id: 'accuracy', label: 'Accuracy' },
  { id: 'provenance', label: 'Provenance' },
]

const toneOf = (s: number) => (s >= 0.95 ? 'correct' : s >= 0.75 ? 'mostly' : s >= 0.4 ? 'partly' : 'wrong')
const openResult = (r: ResultRow) => navigate({ name: 'result', resultId: r.result_id })

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <Card>
      <div style={{ padding: '32px 0', textAlign: 'center', font: 'var(--type-body)', color: 'var(--fg-2)' }}>{children}</div>
    </Card>
  )
}

export function Overview({ data }: { data: ReportData }) {
  const allRuns = useMemo(() => runsOf(data.results), [data])
  const models = useMemo(() => modelsOf(data.results), [data])
  const dates = useMemo(() => [...new Set(allRuns.map((r) => r.date))], [allRuns])

  const [model, setModel] = useState(ALL_MODELS)
  const [range, setRange] = useState(() => ({ from: dates[0], to: dates[dates.length - 1] }))
  const [metric, setMetric] = useState<'overall' | 'accuracy' | 'provenance'>('overall')

  const runs = allRuns.filter(
    (r) => (model === ALL_MODELS || r.model === model) && r.date >= range.from && r.date <= range.to,
  )

  if (allRuns.length === 0) {
    return (
      <>
        <PageHeader title="Overview" />
        <Empty>
          No results yet. Run <code>agent-quiz run</code>, then <code>agent-quiz report</code> again.
        </Empty>
      </>
    )
  }

  const latest = runs[runs.length - 1]
  const previous = runs[runs.length - 2]
  const failing = latest ? latest.results.filter((r) => !passes(r)) : []

  const columns = runColumns(runs)
  const quizzes = quizzesOf(runs.flatMap((r) => r.results))
  const scoreIn = (runIndex: number, quizId: string, key: 'accuracy_score' | 'provenance_score') => {
    const rows = runs[runIndex].results.filter((r) => r.quiz_id === quizId)
    return rows.length ? mean(rows.map((r) => r[key])) : null
  }
  const heatRows = quizzes.map((q) => ({
    label: q.quiz_id,
    sublabel: q.category,
    accuracy: runs.map((_, i) => scoreIn(i, q.quiz_id, 'accuracy_score')),
    provenance: runs.map((_, i) => scoreIn(i, q.quiz_id, 'provenance_score')),
  }))
  const categories = [...new Set(quizzes.map((q) => q.category))]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <PageHeader title="Overview" subtitle={latest ? `Last eval run ${formatRunTime(latest.timestamp)} · ${latest.model}` : undefined}>
        <Select size="sm" icon="cpu" options={[ALL_MODELS, ...models]} value={model} onChange={setModel} />
        <DateRangePicker dates={dates} value={range} onChange={setRange} />
      </PageHeader>

      {!latest ? (
        <Empty>
          No eval runs between {range.from} and {range.to}
          {model === ALL_MODELS ? '' : ` for ${model}`}. Try a wider range.
        </Empty>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
            <Card>
              <ScoreStat
                label="Overall"
                value={latest.overall}
                delta={previous ? latest.overall - previous.overall : undefined}
                caption={previous ? undefined : 'First run in this range'}
                spark={runs.map((r) => r.overall)}
              />
            </Card>
            <Card>
              <ScoreStat
                label="Accuracy"
                value={latest.accuracy}
                delta={previous ? latest.accuracy - previous.accuracy : undefined}
                caption={previous ? undefined : 'First run in this range'}
                spark={runs.map((r) => r.accuracy)}
              />
            </Card>
            <Card>
              <ScoreStat
                label="Provenance"
                value={latest.provenance}
                delta={previous ? latest.provenance - previous.provenance : undefined}
                caption={previous ? undefined : 'First run in this range'}
                spark={runs.map((r) => r.provenance)}
              />
            </Card>
            <Card>
              <ScoreStat
                label="Passed thresholds"
                value={`${latest.passed} / ${latest.results.length}`}
                format="raw"
                caption={failing.length ? `${failing.length} below min score` : 'All met their min score'}
              />
            </Card>
          </div>

          <Card
            title="Scores by eval run"
            subtitle={`${runs.length} runs · click a cell to see that answer`}
            actions={<Tabs items={METRICS} value={metric} onChange={(id) => setMetric(id as typeof metric)} />}
          >
            <Heatmap
              metric={metric}
              showToggle={false}
              rowHeader="Quiz"
              rowLabelWidth={300}
              groupBy="sublabel"
              defaultExpanded={categories}
              rows={heatRows}
              columns={columns}
              onCellClick={(row, column, value) => {
                const run = runs[columns.indexOf(column)]
                const result = value == null ? undefined : run?.results.find((r) => r.quiz_id === row.label)
                if (result) openResult(result)
              }}
            />
          </Card>

          <Card
            title="Below threshold"
            subtitle={`Latest eval run, ${formatRunTime(latest.timestamp)} · ${failing.length} of ${latest.results.length} quizzes below their accuracy or provenance min score`}
          >
            {failing.length === 0 ? (
              <p style={{ margin: 0, font: 'var(--type-body)', color: 'var(--fg-2)' }}>
                Nothing to fix. Your agent was honest this run.
              </p>
            ) : (
              <DataTable
                rowKey="result_id"
                onRowClick={openResult}
                rows={failing}
                columns={[
                  { key: 'quiz_id', label: 'Quiz', mono: true },
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
                    key: 'agent_answer',
                    label: 'Agent said',
                    render: (r: ResultRow) => (
                      <span style={{ font: 'var(--type-small)', color: 'var(--fg-2)' }}>{truncate(r.agent_answer, 90)}</span>
                    ),
                  },
                  {
                    key: 'status',
                    label: '',
                    align: 'right',
                    render: (r: ResultRow) => (
                      <Badge tone={toneOf(accuracyPasses(r) ? r.provenance_score : r.accuracy_score)} dot>
                        {accuracyPasses(r) ? 'Provenance' : 'Accuracy'}
                      </Badge>
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

const truncate = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)
