import { Icon, Switch } from '../ds'
import { href, type Route } from '../router'

const ITEMS = [
  { route: { name: 'overview' } as Route, label: 'Overview', icon: 'layout-dashboard' },
  { route: { name: 'compare' } as Route, label: 'Model comparison', icon: 'git-compare' },
]

// Adapted from the design system's ui_kits/dashboard/Sidebar.jsx. Uses the
// wordmark alone until assets/logo-mark.png is added for the Logo component.
export function Sidebar({
  route,
  theme,
  setTheme,
  generatedAt,
}: {
  route: Route
  theme: 'light' | 'dark'
  setTheme: (t: 'light' | 'dark') => void
  generatedAt: string | null
}) {
  const active = route.name === 'result' ? 'overview' : route.name
  return (
    <aside
      style={{
        width: 208,
        flex: 'none',
        borderRight: '1px solid var(--border-1)',
        background: 'var(--bg-surface)',
        display: 'flex',
        flexDirection: 'column',
        padding: '18px 12px',
        gap: 24,
        position: 'sticky',
        top: 0,
        height: '100vh',
      }}
    >
      <div
        style={{
          padding: '16px 12px',
          borderRadius: 'var(--radius-md)',
          border: '1.5px solid var(--green-300)',
          font: '600 14px/1 var(--font-display)',
          letterSpacing: '-0.02em',
          whiteSpace: 'nowrap',
        }}
      >
        The Honest Agent
      </div>
      <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {ITEMS.map((it) => {
          const on = active === it.route.name
          return (
            <a
              key={it.label}
              href={href(it.route)}
              aria-current={on ? 'page' : undefined}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                height: 36,
                padding: '0 10px',
                borderRadius: 'var(--radius-sm)',
                background: on ? 'var(--accent-soft)' : 'transparent',
                color: on ? 'var(--accent)' : 'var(--fg-2)',
                font: '500 14px/1 var(--font-sans)',
                textDecoration: 'none',
                whiteSpace: 'nowrap',
              }}
            >
              <Icon name={it.icon} size={16} />
              {it.label}
            </a>
          )
        })}
      </nav>
      <div
        style={{
          marginTop: 'auto',
          padding: '12px 10px 0',
          borderTop: '1px solid var(--border-1)',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        <Switch checked={theme === 'dark'} onChange={(v) => setTheme(v ? 'dark' : 'light')} label="Dark mode" />
        {generatedAt ? (
          <span style={{ font: '400 12px/1.4 var(--font-mono)', color: 'var(--fg-3)' }}>
            Generated {generatedAt.slice(0, 16).replace('T', ' ')} UTC
          </span>
        ) : null}
      </div>
    </aside>
  )
}
