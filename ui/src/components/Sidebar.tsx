import { useEffect, useState, type CSSProperties } from 'react'
import { formatRunTime } from '../data/derive'
import { Icon, Logo, Switch } from '../ds'
import { href, type Route } from '../router'

const ITEMS = [
  { route: { name: 'overview' } as Route, label: 'Overview', icon: 'layout-dashboard' },
  { route: { name: 'compare' } as Route, label: 'Model comparison', icon: 'git-compare' },
]
const MINI_KEY = 'honest-agent.sidebarMini'
// Bust crop of design/mascot.svg, matching the design system's logo-mark.
const LOGO_SRC = './logo-mark.svg'

function initialMini(): boolean {
  try {
    return localStorage.getItem(MINI_KEY) === '1'
  } catch {
    return false
  }
}

const iconBtn: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 36,
  height: 36,
  border: 0,
  borderRadius: 'var(--radius-sm)',
  background: 'transparent',
  color: 'var(--fg-2)',
  cursor: 'pointer',
  flex: 'none',
}

// Ported from the design system's ui_kits/dashboard/Sidebar.jsx.
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
  const [hov, setHov] = useState(false)
  const [mini, setMini] = useState(initialMini)
  useEffect(() => {
    try {
      localStorage.setItem(MINI_KEY, mini ? '1' : '0')
    } catch {
      // Storage unavailable; the toggle still works for this visit.
    }
  }, [mini])

  // A result page belongs to neither section (it opens from the overview or the comparison), so nothing is active there.
  const active = route.name
  return (
    <aside
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        width: mini ? 68 : 208,
        transition: 'width var(--dur-base) var(--ease-out)',
        flex: 'none',
        borderRight: '1px solid var(--border-1)',
        background: 'var(--bg-surface)',
        display: 'flex',
        flexDirection: 'column',
        padding: mini ? '18px 10px' : '18px 12px',
        gap: 24,
        position: 'sticky',
        top: 0,
        height: '100vh',
        overflow: 'hidden',
      }}
    >
      <div style={{ position: 'relative' }}>
        <a
          href={href({ name: 'overview' })}
          aria-label="The Honest Agent, go to Overview"
          title={mini ? 'The Honest Agent' : undefined}
          style={{
            color: 'inherit',
            textDecoration: 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: mini ? 'center' : 'flex-start',
            height: mini ? 48 : undefined,
            padding: mini ? 0 : '16px 12px',
            borderRadius: 'var(--radius-md)',
            border: mini ? '1.5px solid transparent' : '1.5px solid var(--green-300)',
            opacity: mini && hov ? 0 : 1,
            transition: 'opacity var(--dur-fast) var(--ease-out)',
          }}
        >
          <Logo markSrc={LOGO_SRC} size={mini ? 28 : 24} textSize={14} wordmark={!mini} />
        </a>
        <button
          type="button"
          onClick={() => setMini(!mini)}
          title={mini ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-label={mini ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!mini}
          onFocus={() => setHov(true)}
          onMouseOver={(e) => {
            e.currentTarget.style.color = 'var(--fg-1)'
            e.currentTarget.style.background = 'var(--bg-sunken)'
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.color = 'var(--fg-2)'
            e.currentTarget.style.background = 'var(--bg-surface)'
          }}
          style={{
            position: 'absolute',
            top: '50%',
            ...(mini
              ? { left: '50%', transform: 'translate(-50%,-50%)', width: 36, height: 36 }
              : { right: 5, transform: 'translateY(-50%)', width: 24, height: 24 }),
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: 0,
            borderRadius: 'var(--radius-sm)',
            background: 'var(--bg-surface)',
            color: 'var(--fg-2)',
            cursor: 'pointer',
            opacity: hov ? 1 : 0,
            pointerEvents: hov ? 'auto' : 'none',
            transition: 'opacity var(--dur-fast) var(--ease-out)',
          }}
        >
          <Icon name={mini ? 'panel-left-open' : 'panel-left-close'} size={16} />
        </button>
      </div>
      <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {ITEMS.map((it) => {
          const on = active === it.route.name
          return (
            <a
              key={it.label}
              href={href(it.route)}
              title={mini ? it.label : undefined}
              aria-label={it.label}
              aria-current={on ? 'page' : undefined}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: mini ? 'center' : 'flex-start',
                gap: 10,
                height: 36,
                padding: mini ? 0 : '0 10px',
                borderRadius: 'var(--radius-sm)',
                background: on ? 'var(--accent-soft)' : 'transparent',
                color: on ? 'var(--accent)' : 'var(--fg-2)',
                font: '500 14px/1 var(--font-sans)',
                textDecoration: 'none',
                whiteSpace: 'nowrap',
              }}
            >
              <Icon name={it.icon} size={16} />
              {mini ? null : it.label}
            </a>
          )
        })}
      </nav>
      <div
        style={{
          marginTop: 'auto',
          padding: mini ? '12px 0 0' : '12px 10px 0',
          borderTop: '1px solid var(--border-1)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: mini ? 'center' : 'stretch',
          gap: 12,
        }}
      >
        {mini ? (
          <button
            type="button"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
            aria-label="Toggle dark mode"
            style={iconBtn}
          >
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={16} />
          </button>
        ) : (
          <>
            <Switch checked={theme === 'dark'} onChange={(v) => setTheme(v ? 'dark' : 'light')} label="Dark mode" />
            {generatedAt ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span style={{ font: '400 12px/1.4 var(--font-sans)', color: 'var(--fg-3)' }}>Generated</span>
                <span style={{ font: '400 12px/1.4 var(--font-mono)', color: 'var(--fg-2)', whiteSpace: 'nowrap' }}>
                  {formatRunTime(generatedAt.slice(0, 16).replace('T', ' '))} UTC
                </span>
              </div>
            ) : null}
          </>
        )}
      </div>
    </aside>
  )
}
