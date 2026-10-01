export interface BadgeProps {
  /** Accuracy tones map to the 4-step scale */
  tone?: 'neutral' | 'accent' | 'correct' | 'mostly' | 'partly' | 'wrong';
  dot?: boolean;
  /** Use Geist Mono (for scores, ids) */
  mono?: boolean;
  children?: React.ReactNode;
}
export declare function Badge(props: BadgeProps): JSX.Element;
