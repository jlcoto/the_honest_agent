export interface SelectOption { value: string; label: string; }
export interface SelectProps {
  label?: string;
  options: (string | SelectOption)[];
  value?: string;
  onChange?: (value: string) => void;
  size?: 'sm' | 'md';
  /** Lucide icon name, leading */
  icon?: string;
}
export declare function Select(props: SelectProps): JSX.Element;
