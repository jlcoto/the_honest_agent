import { useMemo, useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { QuizLabel } from '../components/QuizLabel'
import {
  accuracyPasses,
  agentsOf,
  formatRunDate,
  formatRunTime,
  mean,
  modelsOf,
  passes,
  provenancePasses,
  quizHeatRow,
  quizTitles,
  quizzesOf,
  runColumns,
  runsOf,
  stripMarkdown,
  toCsv,
} from '../data/derive'
import type { ReportData, ResultRow } from '../data/types'
import { Badge, Card, DataTable, DateRangePicker, Heatmap, Icon, IconButton, ScoreCell, ScoreStat, Select, Tabs } from '../ds'
import { navigate } from '../router'

const METRICS = [
  { id: 'overall', label: 'Combined' },
  { id: 'accuracy', label: 'Accuracy' },
  { id: 'provenance', label: 'Provenance' },
]

const toneOf = (s: number) => (s >= 0.95 ? 'correct' : s >= 0.75 ? 'mostly' : s >= 0.4 ? 'partly' : 'wrong')
const openResult = (r: ResultRow) => navigate({ name: 'result', resultId: r.result_id })

function downloadCsv(filename: string, rows: ResultRow[], titles: Map<string, string>) {
  const csv = toCsv(
    ['quiz_id', 'quiz_title', 'category', 'accuracy_score', 'accuracy_min_score', 'provenance_score', 'provenance_min_score', 'failed', 'accuracy_method', 'expected_answer', 'agent_answer'],
    rows.map((r) => [
      r.quiz_id,
      titles.get(r.quiz_id) ?? null,
      r.category,
      r.accuracy_score,
      r.accuracy_min_score,
      r.provenance_score,
      r.provenance_min_score,
      [accuracyPasses(r) ? null : 'accuracy', provenancePasses(r) ? null : 'provenance'].filter(Boolean).join('+'),
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

export function Overview({ data }: { data: ReportData }) {
  const allRuns = useMemo(() => runsOf(data.results), [data])
  const agents = useMemo(() => agentsOf(data.results), [data])
  const titles = useMemo(() => quizTitles(data.results), [data])
  const allDates = useMemo(() => [...new Set(allRuns.map((r) => r.date))], [allRuns])

  // Scores are only meaningful for one agent and one model at a time, so both
  // are always a single pick, defaulting to the latest run's.
  const [agent, setAgent] = useState(() => allRuns.at(-1)?.agent ?? '')
  const agentRuns = allRuns.filter((r) => r.agent === agent)
  const models = modelsOf(agentRuns.flatMap((r) => r.results))
  const [modelPick, setModel] = useState(() => allRuns.at(-1)?.model ?? '')
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
          No results yet. Run <code>agent-quiz run</code>, then <code>agent-quiz report</code> again.
        </Empty>
      </>
    )
  }

  const latest = runs[runs.length - 1]
  const previous = runs[runs.length - 2]
  const failing = latest ? latest.results.filter((r) => !passes(r)) : []

  const columns = runColumns(runs)
  const quizzes = quizzesOf(runs.flatMap((r) => r.results), titles)
  const scoreIn = (runIndex: number, quizId: string, key: 'accuracy_score' | 'provenance_score') => {
    const rows = runs[runIndex].results.filter((r) => r.quiz_id === quizId)
    return rows.length ? mean(rows.map((r) => r[key])) : null
  }
  const heatRows = quizzes.map((q) =>
    quizHeatRow(
      q,
      runs.map((_, i) => scoreIn(i, q.quiz_id, 'accuracy_score')),
      runs.map((_, i) => scoreIn(i, q.quiz_id, 'provenance_score')),
    ),
  )
  const categories = [...new Set(quizzes.map((q) => q.category))]

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
                caption={failing.length ? `${failing.length} below min score` : 'None below min score'}
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
              rowHeader="Quiz"
              rowLabelWidth={360}
              groupBy="category"
              defaultExpanded={categories}
              rows={heatRows}
              columns={columns}
              onCellClick={(row, column, value) => {
                const run = runs[columns.indexOf(column)]
                const quizId = (row as ReturnType<typeof quizHeatRow>).quiz_id
                const result = value == null ? undefined : run?.results.find((r) => r.quiz_id === quizId)
                if (result) openResult(result)
              }}
            />
          </Card>

          <Card
            title="Below threshold"
            subtitle={`Latest eval run, ${formatRunDate(latest.timestamp)} · ${failing.length} ${failing.length === 1 ? 'quiz' : 'quizzes'} failed accuracy or provenance min score`}
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
                    key: 'quiz_id',
                    label: 'Quiz',
                    render: (r: ResultRow) => <QuizLabel quizId={r.quiz_id} title={titles.get(r.quiz_id)} />,
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
                      <span style={{ font: 'var(--type-small)', color: 'var(--fg-2)' }}>{answerPreview(r.agent_answer)}</span>
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
                        {accuracyPasses(r) ? null : (
                          <Badge tone={toneOf(r.accuracy_score)} dot>
                            Accuracy
                          </Badge>
                        )}
                        {provenancePasses(r) ? null : (
                          <Badge tone={toneOf(r.provenance_score)} dot>
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
