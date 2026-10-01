import { useEffect, useState } from 'react'
import { loadReportData } from './data/load'
import type { ReportData } from './data/types'
import { AccuracyLegend, Card, ScoreStat } from './ds'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: ReportData }

const mean = (xs: number[]) => xs.reduce((s, x) => s + x, 0) / xs.length

function Summary({ data }: { data: ReportData }) {
  const { results } = data
  const runs = new Set(results.map((r) => r.run_id)).size
  const passed = results.filter((r) => r.accuracy_score >= (r.accuracy_min_score ?? 1)).length
  return (
    <Card title="All runs" subtitle={`${passed} of ${results.length} answers met their accuracy threshold across ${runs} runs.`}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 'var(--space-4)' }}>
        <ScoreStat label="Accuracy" value={mean(results.map((r) => r.accuracy_score))} />
        <ScoreStat label="Provenance" value={mean(results.map((r) => r.provenance_score))} />
      </div>
      <AccuracyLegend compact />
    </Card>
  )
}

function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })

  useEffect(() => {
    loadReportData()
      .then((data) => setState({ status: 'ready', data }))
      .catch((err: unknown) =>
        setState({ status: 'error', message: err instanceof Error ? err.message : String(err) }),
      )
  }, [])

  return (
    <main style={{ maxWidth: 'var(--content-max)', margin: '0 auto', padding: 'var(--space-8) var(--space-8)' }}>
      <h1 style={{ font: 'var(--type-h1)', letterSpacing: 'var(--ls-display)', margin: '0 0 var(--space-6)' }}>
        Agent quiz report
      </h1>
      {state.status === 'loading' && <p style={{ color: 'var(--fg-3)' }}>Loading…</p>}
      {state.status === 'error' && (
        <p role="alert">
          {state.message} If you opened this file directly, run <code>agent-quiz serve</code> instead.
        </p>
      )}
      {state.status === 'ready' && <Summary data={state.data} />}
    </main>
  )
}

export default App
