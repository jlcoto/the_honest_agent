export interface HeatmapRow {
  label: string;
  /** Secondary line under the label, in mono. Typically the row's identifier (e.g. a eval_id) when `label` is a human-readable title. */
  sublabel?: string;
  /** Per-column accuracy 0–1 (enables Combined/Accuracy/Provenance toggle) */
  accuracy?: (number | null)[];
  /** Per-column provenance 0–1 */
  provenance?: (number | null)[];
  /** Single-metric mode: per-column score 0–1 */
  values?: (number | null)[];
}
/**
 * @startingPoint section="Data" subtitle="FiveThirtyEight-style eval × run score table" viewport="700x420"
 */
export interface HeatmapProps {
  rows: HeatmapRow[];
  /** Column labels, rendered rotated 45°. "YYYY-MM-DD HH:MM" timestamps show the date only in the header; the full timestamp appears on hover. */
  columns: string[];
  /** Controlled metric; overall (label "Combined") = mean(accuracy, provenance) */
  metric?: 'overall' | 'accuracy' | 'provenance';
  defaultMetric?: 'overall' | 'accuracy' | 'provenance';
  onMetricChange?: (m: string) => void;
  /** Defaults to true when rows carry accuracy + provenance */
  showToggle?: boolean;
  /** Right-hand column averaging all runs (sticky) */
  showSummary?: boolean;
  summaryLabel?: string;
  /** Row key to group by (e.g. "sublabel" or "category"). Group rows show the average of their evals; click to expand. */
  groupBy?: string;
  /** Header word for groups, default "Category" */
  groupLabel?: string;
  /** Group names expanded on first render */
  defaultExpanded?: string[];
  /** Used in the group tooltip: "2 of 4 evals below 80%". Default 0.8 */
  threshold?: number;
  /** Bottom row averaging every eval per run (default true) */
  showTotals?: boolean;
  /** Default "Overall" */
  totalsLabel?: string;
  /** Uppercase header over the row labels */
  rowHeader?: string;
  cellWidth?: number;
  cellHeight?: number;
  rowLabelWidth?: number;
  /** Bucket legend under the table; off by default */
  showLegend?: boolean;
  onCellClick?: (row: HeatmapRow, column: string, value: number | null, metric: string) => void;
}
export declare function Heatmap(props: HeatmapProps): JSX.Element;
