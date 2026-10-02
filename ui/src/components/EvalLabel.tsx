// Matches the "Eval" column in the design system's ui_kits/dashboard/Overview.jsx.
/** An eval's title with its eval_id in mono underneath, or the eval_id alone when it has no title. */
export function EvalLabel({ evalId, title }: { evalId: string; title: string | null | undefined }) {
  if (!title) return <span style={{ fontFamily: 'var(--font-mono)' }}>{evalId}</span>
  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span>{title}</span>
      <span style={{ font: '400 11px/1.3 var(--font-mono)', color: 'var(--fg-3)' }}>{evalId}</span>
    </span>
  )
}
