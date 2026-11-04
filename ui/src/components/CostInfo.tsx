import type { ReactNode } from 'react'
import { InfoLabel } from './InfoLabel'

export const COST_NOTE =
  "An estimate: each model call's tokens × the provider's published prices on the day of the run. Your provider's bill is the real figure."

/** A cost's words with an (i), explaining that it's an estimate. */
export function CostInfo({ children, side }: { children: ReactNode; side?: 'top' | 'bottom' }) {
  return (
    <InfoLabel note={COST_NOTE} side={side}>
      {children}
    </InfoLabel>
  )
}
