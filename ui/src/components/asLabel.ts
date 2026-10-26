import type { ReactNode } from 'react'

/** The design system types some labels as strings, but renders any node: for a label with an (i) in it. */
export const asLabel = (node: ReactNode) => node as unknown as string
