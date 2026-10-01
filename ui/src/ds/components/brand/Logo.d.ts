export interface LogoProps {
  /** Path to assets/logo-mark.png relative to the page */
  markSrc?: string;
  /** Mark height in px (mark is ~1.2:1); wordmark scales to 50% */
  size?: number;
  wordmark?: boolean;
  /** Wordmark font size in px. Default: 50% of size */
  textSize?: number;
  stacked?: boolean;
  /** Light wordmark for dark surfaces (e.g. --green-800) */
  inverse?: boolean;
}
export declare function Logo(props: LogoProps): JSX.Element;
