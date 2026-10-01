export interface DateRange { from: string; to: string; }
export interface DateRangePreset { label: string; days: number; }
export interface DateRangePickerProps {
  /** Selected range, ISO dates (YYYY-MM-DD) */
  value?: DateRange;
  onChange?: (range: DateRange) => void;
  /** ISO dates that have data; shown with a dot and enable an "All eval runs" preset */
  dates?: string[];
  /** Quick ranges ending today. Default last 7 / 30 / 90 days */
  presets?: DateRangePreset[];
  /** ISO date treated as today; later days are disabled. Default: the real today */
  today?: string;
  /** Popover alignment against the trigger. Default "right" */
  align?: 'left' | 'right';
}
export declare function DateRangePicker(props: DateRangePickerProps): JSX.Element;
