// Matches the "Quiz" column in the design system's ui_kits/dashboard/Overview.jsx.
/** A quiz's title with its quiz_id in mono underneath, or the quiz_id alone when it has no title. */
export function QuizLabel({ quizId, title }: { quizId: string; title: string | null | undefined }) {
  if (!title) return <span style={{ fontFamily: 'var(--font-mono)' }}>{quizId}</span>
  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span>{title}</span>
      <span style={{ font: '400 11px/1.3 var(--font-mono)', color: 'var(--fg-3)' }}>{quizId}</span>
    </span>
  )
}
