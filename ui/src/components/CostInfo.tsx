import type { ReactNode } from 'react'
import { Icon, Tooltip } from '../ds'

export const COST_NOTE =
  "An estimate: each model call's tokens × the provider's published prices on the day of the run. Your provider's bill is the real figure."

/** A cost's words with an (i), explaining that it's an estimate. The whole phrase is the hover target, so the
 * tooltip, centred on it, stays on screen even when the (i) wraps to the edge of a phone. The design system's
 * Tooltip doesn't wrap, so the note gets a fixed width here. */
export function CostInfo({ children, side }: { children: ReactNode; side?: 'top' | 'bottom' }) {
  return (
    <Tooltip side={side} content={<span style={{ display: 'block', width: 200, whiteSpace: 'normal' }}>{COST_NOTE}</span>}>
      <span tabIndex={0} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap', cursor: 'help' }}>
        {children}
        <span role="img" aria-label={COST_NOTE} style={{ display: 'inline-flex', color: 'var(--fg-3)' }}>
          <Icon name="info" size={14} />
        </span>
      </span>
    </Tooltip>
  )
}
