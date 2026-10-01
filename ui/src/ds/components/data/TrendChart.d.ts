export interface TrendSeries { id?: string; label: string; /** 0–1, null for gaps */ values: (number | null)[]; color?: string; }
/**
 * @startingPoint section="Data" subtitle="Accuracy over runs with min-score threshold" viewport="700x280"
 */
export interface TrendChartProps {
  series: TrendSeries[];
  /** X-axis labels (run dates) */
  labels: string[];
  /** Dashed min_score line */
  threshold?: number;
  height?: number;
  min?: number;
  max?: number;
  /** Single-series: color dots by accuracy bucket */
  colorDots?: boolean;
}
export declare function TrendChart(props: TrendChartProps): JSX.Element;
