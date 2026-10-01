// The vendored .d.ts files use the global `JSX.Element`, which React 19's
// types no longer declare globally.
import type { JSX as ReactJSX } from 'react'

declare global {
  namespace JSX {
    type Element = ReactJSX.Element
  }
}
