export interface TabItem { id: string; label: string; }
export interface TabsProps {
  items: TabItem[];
  value: string;
  onChange?: (id: string) => void;
  /** segmented = compact range/metric switcher; underline = page-level tabs */
  variant?: 'segmented' | 'underline';
}
export declare function Tabs(props: TabsProps): JSX.Element;
