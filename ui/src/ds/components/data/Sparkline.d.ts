export interface SparklineProps {
  /** Scores 0–1 */
  values: number[];
  width?: number;
  height?: number;
  color?: string;
  min?: number;
  max?: number;
  /** End dot colored by accuracy bucket of the last value */
  showEnd?: boolean;
}
export declare function Sparkline(props: SparklineProps): JSX.Element;
