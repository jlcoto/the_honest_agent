export interface IconProps {
  /** Lucide icon name, kebab-case (e.g. "layout-dashboard") */
  name: string;
  /** px, default 16 */
  size?: number;
  /** CSS color, default currentColor */
  color?: string;
  title?: string;
  style?: React.CSSProperties;
}
export declare function Icon(props: IconProps): JSX.Element;
