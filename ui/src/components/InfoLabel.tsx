import type { ReactNode } from 'react'
import { Icon, Tooltip } from '../ds'

/** Words with an (i) that explains them on hover or focus. The whole phrase is the hover target, so the tooltip,
 * centred on it, stays on screen even when the (i) wraps to the edge of a phone. The design system's Tooltip
 * doesn't wrap, so the note gets a fixed width here. */
export function InfoLabel({ children, note, side }: { children: ReactNode; note: string; side?: 'top' | 'bottom' }) {
  return (
    <Tooltip side={side} content={<span style={{ display: 'block', width: 200, whiteSpace: 'normal' }}>{note}</span>}>
      <span tabIndex={0} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap', cursor: 'help' }}>
        {children}
        <span role="img" aria-label={note} style={{ display: 'inline-flex', color: 'var(--fg-3)' }}>
          <Icon name="info" size={14} />
        </span>
      </span>
    </Tooltip>
  )
}
