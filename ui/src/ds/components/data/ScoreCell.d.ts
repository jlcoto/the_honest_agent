export interface ScoreCellProps {
  /** 0–1 */
  score: number | null;
  /** min_score tick; value renders in wrong-ink when below */
  threshold?: number;
  /** Bar width px, default 64 */
  width?: number;
}
export declare function ScoreCell(props: ScoreCellProps): JSX.Element;
