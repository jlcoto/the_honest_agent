/**
 * @startingPoint section="Data" subtitle="Headline accuracy metric with delta and sparkline" viewport="700x200"
 */
export interface ScoreStatProps {
  label: string;
  /** 0–1 when format="percent", otherwise shown verbatim */
  value: number | string;
  format?: 'percent' | 'raw';
  /** Change as a fraction (0.021 → +2.1 pp) */
  delta?: number;
  deltaLabel?: string;
  caption?: string;
  /** Optional sparkline values 0–1 */
  spark?: number[];
  size?: 'md' | 'lg';
}
export declare function ScoreStat(props: ScoreStatProps): JSX.Element;
