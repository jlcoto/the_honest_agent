/**
 * @startingPoint section="Data" subtitle="Headline accuracy metric with delta and sparkline" viewport="700x200"
 */
export interface ScoreStatProps {
  /** Text, or text with an inline element such as an info icon */
  label: React.ReactNode;
  /** 0–1 when format="percent", otherwise shown verbatim ("17 / 25" for a count) */
  value: number | string;
  /** "count": a value like "17 / 25", whose delta is in whole units (+1, −2, ±0) and whose caption shows next to the delta */
  format?: 'percent' | 'raw' | 'count';
  /** Change as a fraction (0.021 → +2.1 pp); with format="count", in units (1 → +1) */
  delta?: number;
  deltaLabel?: string;
  /** Formats the delta yourself (e.g. a cost: d => "+$0.012"); ±0 is still greyed */
  formatDelta?: (delta: number) => string;
  /** A rise reads as worse (red) and a fall as better, e.g. for a cost. Default false */
  lowerIsBetter?: boolean;
  /** Shown when there's no delta; with format "raw" or "count", next to the delta (e.g. the percentage, a per-eval cost) */
  caption?: string;
  /** A line under the rest, in the wrong-ink colour (e.g. "2 stopped with an error") */
  alert?: string;
  /** Optional sparkline values, 0–1 unless sparkRange says otherwise */
  spark?: number[];
  /** [min, max] of the sparkline's scale, for values that aren't 0–1 scores. Default [0, 1] */
  sparkRange?: [number, number];
  size?: 'md' | 'lg';
}
export declare function ScoreStat(props: ScoreStatProps): JSX.Element;
