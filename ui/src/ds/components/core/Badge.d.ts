export interface BadgeProps {
  /** Accuracy tones map to the 4-step scale */
  tone?: 'neutral' | 'accent' | 'correct' | 'mostly' | 'partly' | 'wrong';
  dot?: boolean;
  /** Use Geist Mono (for scores, ids) */
  mono?: boolean;
  /** "sm" for a pill nested under a larger one, e.g. one source inside a card's overall result */
  size?: 'md' | 'sm';
  /** Never wider than its container: a longer label ends in "…" and shows in full on hover. */
  children?: React.ReactNode;
}
export declare function Badge(props: BadgeProps): JSX.Element;
