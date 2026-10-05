import { useState, type ReactNode } from 'react'
import { formatRunDate, formatRunTime, pct, type Run } from '../data/derive'

type Metric = 'overall' | 'accuracy' | 'provenance'
const METRIC_LABEL: Record<Metric, string> = { overall: 'Combined', accuracy: 'Accuracy', provenance: 'Provenance' }

/**
 * The design system's series palette, assigned by first appearance: each model takes the next --series color the
 * first time it ever ran (across all agents) and keeps it, so a model's color never changes between screens and a
 * new model never repaints the others. Models past the fifth get --border-2 instead of a repeated color.
 */
export function seriesColors(allRuns: Run[]): Map<string, string> {
  const firstSeen = [...new Set([...allRuns].sort((a, b) => a.timestamp.localeCompare(b.timestamp)).map((r) => r.model))]
  return new Map(firstSeen.map((m, i) => [m, i < 5 ? `var(--series-${i + 1})` : 'var(--border-2)']))
}

export const SCORES_OVER_TIME_NOTE =
  "Each point is a model's last run of that day. When a model ran several times in a day, only the last run is shown; hover a point to see how many runs that day had."

interface Point {
  /** Index of the run's day among the days shown. */
  day: number
  run: Run
  /** Runs this model had that day; only the last is plotted. */
  runsThatDay: number
  value: number
}

// Geometry and font sizes in viewBox units; the SVG scales up to the card's width (~1.25x at full width).
const W = 980
const ROW = 74
const STRIP = 52
// Inner padding so a 0% or 100% point (radius 4) sits just inside the strip edge, still reading as 0/100.
const PAD = 4
const LEFT = 230
const RIGHT = 24
const AXIS = 26

/**
 * Small multiples: one strip per model on a shared day axis and 0–100% scale. Days with any run are evenly
 * spaced (runs often come in bursts minutes apart, then nothing for days), and each point is that day's last run.
 * Each model keeps one series color (see seriesColors); the name label stays in text ink.
 */
export function ScoresOverTime({
  runs,
  models,
  metric,
  colors,
}: {
  runs: Run[]
  models: string[]
  metric: Metric
  colors: Map<string, string>
}) {
  const [tip, setTip] = useState<{ x: number; y: number; body: ReactNode } | null>(null)
  const days = [...new Set(runs.map((r) => r.date))].sort()
  const slot = (W - LEFT - RIGHT) / Math.max(days.length, 1)
  const x = (day: number) => LEFT + (day + 0.5) * slot
  // A tick per day, skipping any that would sit within 52 units of the previous one so labels never collide.
  const ticks: number[] = []
  days.forEach((_, i) => {
    if (!ticks.length || (i - ticks[ticks.length - 1]) * slot >= 52) ticks.push(i)
  })
  const H = models.length * ROW + AXIS

  const pointsOf = (model: string): Point[] => {
    const byDay = new Map<string, Run[]>()
    for (const run of runs.filter((r) => r.model === model)) byDay.set(run.date, [...(byDay.get(run.date) ?? []), run])
    return [...byDay.entries()]
      .map(([date, dayRuns]) => {
        const run = dayRuns.reduce((a, b) => (b.timestamp > a.timestamp ? b : a))
        return { day: days.indexOf(date), run, runsThatDay: dayRuns.length, value: run[metric] }
      })
      .sort((a, b) => a.day - b.day)
  }

  return (
    <div style={{ position: 'relative' }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Scores over time by model" onMouseLeave={() => setTip(null)}>
        {models.map((model, i) => {
          const top = i * ROW + 8
          const y = (v: number) => top + PAD + (1 - v) * (STRIP - 2 * PAD)
          const points = pointsOf(model)
          return (
            <g key={model}>
              <rect x={LEFT} y={top} width={W - LEFT - RIGHT} height={STRIP} rx={6} fill="var(--bg-sunken)" opacity={0.55} />
              <line x1={LEFT} x2={W - RIGHT} y1={y(0.5)} y2={y(0.5)} stroke="var(--chart-grid)" />
              <circle cx={5} cy={top + STRIP / 2} r={4} fill={colors.get(model)} />
              <text x={16} y={top + STRIP / 2 + 4} style={{ font: '500 10.5px var(--font-mono)', fill: 'var(--fg-1)' }}>
                {model}
              </text>
              <polyline
                fill="none"
                stroke={colors.get(model)}
                strokeWidth={2}
                strokeLinejoin="round"
                points={points.map((p) => `${x(p.day)},${y(p.value)}`).join(' ')}
              />
              {points.map((p) => (
                <circle key={p.run.run_id} cx={x(p.day)} cy={y(p.value)} r={4} fill={colors.get(model)} stroke="var(--bg-surface)" strokeWidth={2} />
              ))}
              {/* Hit targets bigger than the marks. */}
              {points.map((p) => (
                <circle
                  key={`hit-${p.run.run_id}`}
                  cx={x(p.day)}
                  cy={y(p.value)}
                  r={11}
                  fill="transparent"
                  onMouseEnter={() =>
                    setTip({
                      x: (x(p.day) / W) * 100,
                      y: (y(p.value) / H) * 100,
                      body: (
                        <>
                          <b style={{ fontWeight: 500 }}>{model}</b>
                          <br />
                          {formatRunTime(p.run.timestamp, { year: false })} · {p.run.results.length}{' '}
                          {p.run.results.length === 1 ? 'eval' : 'evals'}
                          {p.runsThatDay > 1 ? ` · last of ${p.runsThatDay} runs that day` : ''}
                          <br />
                          {METRIC_LABEL[metric]} {pct(p.value)} · {p.run.passed}/{p.run.results.length} passed thresholds
                        </>
                      ),
                    })
                  }
                />
              ))}
            </g>
          )
        })}
        {ticks.map((i) => (
          <text key={i} x={x(i)} y={H - 6} textAnchor="middle" style={{ font: '400 9px var(--font-mono)', fill: 'var(--chart-axis)' }}>
            {formatRunDate(days[i])}
          </text>
        ))}
      </svg>
      {tip ? (
        <div
          role="tooltip"
          style={{
            position: 'absolute',
            left: `${tip.x}%`,
            top: `${tip.y}%`,
            transform: 'translate(-50%, calc(-100% - 10px))',
            pointerEvents: 'none',
            zIndex: 20,
            padding: '6px 8px',
            borderRadius: 'var(--radius-xs)',
            background: 'var(--bg-inverse)',
            color: 'var(--fg-inverse)',
            font: '400 12px/1.45 var(--font-sans)',
            whiteSpace: 'nowrap',
            boxShadow: 'var(--shadow-2)',
          }}
        >
          {tip.body}
        </div>
      ) : null}
    </div>
  )
}
