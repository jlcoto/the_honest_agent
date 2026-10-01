import type { ReactNode } from 'react'

// Ported from the design system's ui_kits/dashboard/PageHeader.jsx.
export function PageHeader({ title, subtitle, children }: { title: ReactNode; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <header style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
        <h1 style={{ margin: 0, font: 'var(--type-h1)', letterSpacing: '-0.01em', overflowWrap: 'anywhere' }}>{title}</h1>
        {subtitle ? <p style={{ margin: 0, font: 'var(--type-small)', color: 'var(--fg-3)' }}>{subtitle}</p> : null}
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>{children}</div>
    </header>
  )
}
