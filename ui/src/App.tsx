import { useEffect, useState } from 'react'
import { Sidebar } from './components/Sidebar'
import { loadReportData } from './data/load'
import type { ReportData } from './data/types'
import { useRoute } from './router'
import { Compare } from './views/Compare'
import { Overview } from './views/Overview'
import { ResultDetail } from './views/ResultDetail'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: ReportData }

type Theme = 'light' | 'dark'
const THEME_KEY = 'honest-agent.theme'

function initialTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const route = useRoute()

  useEffect(() => {
    loadReportData()
      .then((data) => setState({ status: 'ready', data }))
      .catch((err: unknown) =>
        setState({ status: 'error', message: err instanceof Error ? err.message : String(err) }),
      )
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      // Storage can be unavailable (private windows, blocked site data); the toggle still works for this visit.
    }
  }, [theme])

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar
        route={route}
        theme={theme}
        setTheme={setTheme}
        generatedAt={state.status === 'ready' ? state.data.generated_at : null}
      />
      <main style={{ flex: 1, minWidth: 0, padding: '28px 32px' }}>
        <div style={{ maxWidth: 'var(--content-max)', margin: '0 auto' }}>
          {state.status === 'loading' && <p style={{ color: 'var(--fg-3)' }}>Loading…</p>}
          {state.status === 'error' && (
            <p role="alert">
              {state.message} If you opened this file directly, run <code>honest-agent serve</code> instead.
            </p>
          )}
          {state.status === 'ready' && route.name === 'overview' && <Overview data={state.data} />}
          {state.status === 'ready' && route.name === 'compare' && <Compare data={state.data} />}
          {state.status === 'ready' && route.name === 'result' && (
            <ResultDetail data={state.data} resultId={route.resultId} />
          )}
        </div>
      </main>
    </div>
  )
}

export default App
