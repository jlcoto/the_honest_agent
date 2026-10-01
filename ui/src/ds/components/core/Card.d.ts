/**
 * @startingPoint section="Core" subtitle="Chart / content card with title and actions" viewport="700x260"
 */
export interface CardProps {
  title?: string;
  subtitle?: string;
  /** Right-aligned header controls */
  actions?: React.ReactNode;
  /** px, default 20 */
  padding?: number;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export declare function Card(props: CardProps): JSX.Element;
