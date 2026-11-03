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
  /** Shown when there's no delta; with format="count", next to the delta (e.g. the percentage) */
  caption?: string;
  /** A line under the rest, in the wrong-ink colour (e.g. "2 stopped with an error") */
  alert?: string;
  /** Optional sparkline values 0–1 */
  spark?: number[];
  size?: 'md' | 'lg';
}
export declare function ScoreStat(props: ScoreStatProps): JSX.Element;
