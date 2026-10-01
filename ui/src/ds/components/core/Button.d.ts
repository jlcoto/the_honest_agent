/**
 * @startingPoint section="Core" subtitle="Primary, secondary and ghost buttons" viewport="700x220"
 */
export interface ButtonProps {
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'sm' | 'md';
  /** Lucide icon name shown before the label */
  icon?: string;
  iconRight?: string;
  disabled?: boolean;
  type?: 'button' | 'submit';
  onClick?: (e: any) => void;
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export declare function Button(props: ButtonProps): JSX.Element;
