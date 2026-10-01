export interface InputProps {
  label?: string;
  /** Lucide icon name, leading */
  icon?: string;
  placeholder?: string;
  value?: string;
  onChange?: (e: any) => void;
  type?: string;
  hint?: string;
  invalid?: boolean;
  disabled?: boolean;
}
export declare function Input(props: InputProps): JSX.Element;
