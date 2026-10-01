export interface IconButtonProps {
  /** Lucide icon name */
  icon: string;
  /** Accessible label (also tooltip) */
  label: string;
  variant?: 'ghost' | 'secondary';
  size?: 'sm' | 'md';
  active?: boolean;
  disabled?: boolean;
  onClick?: (e: any) => void;
}
export declare function IconButton(props: IconButtonProps): JSX.Element;
