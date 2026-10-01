export interface AccuracyCounts { correct?: number; mostly?: number; partly?: number; wrong?: number; }
export interface AccuracyBarProps {
  counts: AccuracyCounts;
  /** px, default 10 */
  height?: number;
  showLegend?: boolean;
  showTotal?: boolean;
}
export declare function AccuracyBar(props: AccuracyBarProps): JSX.Element;
